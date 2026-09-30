import hmac
import json
import logging
import re
from collections import OrderedDict
from datetime import datetime, timezone
from threading import Lock

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from fastapi.responses import JSONResponse, PlainTextResponse

from app import extractor, sheets, whatsapp
from app.config import get_settings

logger = logging.getLogger("invoice-bot")
app = FastAPI(title="WhatsApp invoice reader")

# Meta delivers at least once, so the same message can arrive twice. This in-memory set is enough for a
# prototype; it is lost on restart and not shared between workers (use a database or Redis for real use).
_seen: OrderedDict[str, None] = OrderedDict()
_seen_lock = Lock()
_SEEN_LIMIT = 5000

MAX_BODY_BYTES = 5 * 1024 * 1024  # Meta's webhook payloads are at most ~3 MB
_SIGNATURE_FORMAT = re.compile(r"sha256=[0-9a-f]{64}")
IGNORED_MESSAGE_TYPES = {"reaction", "system"}  # e.g. a thumbs-up on our reply: nothing to answer


def _first_delivery(message_id: str) -> bool:
    with _seen_lock:
        if message_id in _seen:
            return False
        _seen[message_id] = None
        while len(_seen) > _SEEN_LIMIT:
            _seen.popitem(last=False)
        return True


def handle_message(message: dict, phone_number_id: str, sender: str) -> None:
    """Runs after the webhook has answered 200: download, extract, save, then reply on WhatsApp."""

    def reply(text: str) -> None:
        try:
            whatsapp.send_text(phone_number_id, sender, text, reply_to=message.get("id"))
        except Exception:
            logger.exception("Could not send WhatsApp reply to %s", sender)

    message_type = message.get("type")
    if message_type in IGNORED_MESSAGE_TYPES:
        return
    media = message.get(message_type) if message_type in ("document", "image") else None
    if not isinstance(media, dict) or not media.get("id"):
        reply("👋 Send me an invoice as a PDF (or a photo) and I'll add it to the spreadsheet.")
        return

    reply("📄 Got it! Reading your invoice…")
    try:
        data = whatsapp.download_media(media["id"])
        mime_type = extractor.sniff_mime(data)
        if not mime_type:
            reply("Please send the invoice as a PDF, JPG, PNG or WebP file.")
            return
        invoice = extractor.extract_invoice(data, mime_type)
        sheets.append_invoice(invoice, sender, datetime.now(timezone.utc))
    except whatsapp.MediaTooLarge:
        reply("❌ That file is too large (max 15 MB).")
        return
    except Exception:
        logger.exception("Failed to process invoice from %s", sender)
        reply("❌ Sorry, I couldn't read that invoice. Please try another file.")
        return

    summary = (
        f"✅ Saved invoice {invoice.invoice_number or '(no number)'} · "
        f"{invoice.supplier_name or 'unknown supplier'} · "
        f"{invoice.currency or ''} {invoice.total if invoice.total is not None else '?'}".strip()
    )
    warnings = invoice.warnings()
    if warnings:
        summary += "\n⚠️ Please check: " + "; ".join(warnings)
    reply(summary)


def _messages_in(payload) -> list[tuple[dict, str, str]]:
    """Pick (message, phone_number_id, sender) out of Meta's nested envelope; log failed deliveries."""
    found = []
    entries = payload.get("entry") if isinstance(payload, dict) else None
    for entry in entries if isinstance(entries, list) else []:
        for change in entry.get("changes") or []:
            value = change.get("value") if change.get("field") == "messages" else None
            if not isinstance(value, dict):
                continue
            for status in value.get("statuses") or []:
                if status.get("status") == "failed":
                    logger.warning("WhatsApp delivery failed: %s", status.get("errors"))
            contacts = value.get("contacts") or [{}]
            phone_number_id = (value.get("metadata") or {}).get("phone_number_id", "")
            for message in value.get("messages") or []:
                # "from" is the phone number; users with a WhatsApp username may only have a scoped ID.
                sender = message.get("from") or message.get("from_user_id") or contacts[0].get("user_id")
                if sender and phone_number_id and message.get("id"):
                    found.append((message, phone_number_id, sender))
    return found


async def _read_capped_body(request: Request) -> bytes:
    """Read the request body, refusing anything over MAX_BODY_BYTES (this runs before authentication)."""
    declared = request.headers.get("content-length", "")
    if declared.isdigit() and int(declared) > MAX_BODY_BYTES:
        raise HTTPException(status_code=413, detail="Body too large")
    chunks, total = [], 0
    async for chunk in request.stream():  # also covers chunked uploads that have no Content-Length
        total += len(chunk)
        if total > MAX_BODY_BYTES:
            raise HTTPException(status_code=413, detail="Body too large")
        chunks.append(chunk)
    return b"".join(chunks)


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.get("/whatsapp/webhook")
def verify_webhook(request: Request) -> Response:
    """Meta's one-time handshake when you save the callback URL in the App Dashboard."""
    params = request.query_params
    expected = get_settings().whatsapp_verify_token
    token = params.get("hub.verify_token", "")
    challenge = params.get("hub.challenge")
    if (
        expected
        and params.get("hub.mode") == "subscribe"
        and challenge is not None
        and hmac.compare_digest(token.encode(), expected.encode())
    ):
        return PlainTextResponse(challenge)  # the bare challenge, not JSON
    return PlainTextResponse("Forbidden", status_code=403)


@app.post("/whatsapp/webhook")
async def receive_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    signature = request.headers.get("X-Hub-Signature-256", "")
    if not _SIGNATURE_FORMAT.fullmatch(signature):  # cheap check first: don't read a body nobody vouches for
        raise HTTPException(status_code=403, detail="Missing or malformed signature")
    raw_body = await _read_capped_body(request)  # the signature covers the exact bytes, so verify before parsing
    if not whatsapp.is_valid_signature(raw_body, signature):
        raise HTTPException(status_code=403, detail="Invalid signature")
    try:
        payload = json.loads(raw_body)
    except ValueError:
        raise HTTPException(status_code=400, detail="Body is not JSON")

    for message, phone_number_id, sender in _messages_in(payload):
        if _first_delivery(message["id"]):
            background_tasks.add_task(handle_message, message, phone_number_id, sender)
    return JSONResponse({"status": "ok"})  # always 200 for valid calls, or Meta keeps retrying
