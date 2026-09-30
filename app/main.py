import logging
from datetime import datetime, timezone

from fastapi import BackgroundTasks, FastAPI, HTTPException, Request, Response
from twilio.twiml.messaging_response import MessagingResponse

from app import extractor, sheets, whatsapp
from app.config import get_settings

logger = logging.getLogger("invoice-bot")
app = FastAPI(title="WhatsApp invoice reader")

MAX_BYTES = 15 * 1024 * 1024  # Gemini accepts up to ~20 MB of inline data per request


def _twiml(text: str) -> Response:
    reply = MessagingResponse()
    reply.message(text)
    return Response(content=str(reply), media_type="application/xml")


def process_invoice(sender: str, media_url: str, mime_type: str) -> None:
    """Runs after the webhook has replied: download, extract, save, then message the result."""
    try:
        data = whatsapp.download_media(media_url)
        if len(data) > MAX_BYTES:
            whatsapp.send_whatsapp(sender, "❌ That file is too large (max 15 MB).")
            return
        invoice = extractor.extract_invoice(data, mime_type)
        sheets.append_invoice(invoice, sender, datetime.now(timezone.utc))
        summary = (
            f"✅ Saved invoice {invoice.invoice_number or '(no number)'} · "
            f"{invoice.supplier_name or 'unknown supplier'} · "
            f"{invoice.currency or ''} {invoice.total if invoice.total is not None else '?'}".strip()
        )
        warnings = invoice.warnings()
        if warnings:
            summary += "\n⚠️ Please check: " + "; ".join(warnings)
        whatsapp.send_whatsapp(sender, summary)
    except Exception:
        logger.exception("Failed to process invoice from %s", sender)
        try:
            whatsapp.send_whatsapp(sender, "❌ Sorry, I couldn't read that invoice. Please try another file.")
        except Exception:
            logger.exception("Could not send the error message either")


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/whatsapp/webhook")
async def whatsapp_webhook(request: Request, background_tasks: BackgroundTasks) -> Response:
    form = dict(await request.form())

    base_url = get_settings().public_base_url
    if base_url:
        signature = request.headers.get("X-Twilio-Signature", "")
        if not whatsapp.is_valid_signature(f"{base_url}/whatsapp/webhook", form, signature):
            raise HTTPException(status_code=403, detail="Invalid Twilio signature")

    sender = str(form.get("From", ""))
    if int(form.get("NumMedia") or 0) < 1:
        return _twiml("👋 Send me an invoice as a PDF (or a photo) and I'll add it to the spreadsheet.")

    mime_type = str(form.get("MediaContentType0", ""))
    if mime_type not in extractor.SUPPORTED_MIME_TYPES:
        return _twiml("Please send the invoice as a PDF, JPG, PNG or WebP file.")

    background_tasks.add_task(process_invoice, sender, str(form["MediaUrl0"]), mime_type)
    return _twiml("📄 Got it! Reading your invoice…")
