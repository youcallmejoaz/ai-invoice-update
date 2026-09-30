"""Thin client for the WhatsApp Cloud API (Meta Graph API)."""
import hashlib
import hmac
import logging

import httpx

from app.config import get_settings

logger = logging.getLogger("invoice-bot")

MAX_MEDIA_BYTES = 15 * 1024 * 1024  # Gemini accepts up to ~20 MB of inline data per request
TIMEOUT_SECONDS = 30
USER_AGENT = "invoice-bot/0.1"


class MediaTooLarge(Exception):
    pass


def _client() -> httpx.Client:
    return httpx.Client(timeout=TIMEOUT_SECONDS, follow_redirects=True)


def _graph_url(path: str) -> str:
    return f"https://graph.facebook.com/{get_settings().graph_api_version}/{path}"


def _auth_header() -> dict:
    return {"Authorization": f"Bearer {get_settings().whatsapp_access_token}"}


def _check(response: httpx.Response) -> None:
    """Like raise_for_status, but logs Meta's error body first (it holds the error code)."""
    if response.is_error:
        response.read()
        logger.error("Graph API answered %s: %s", response.status_code, response.text[:500])
    response.raise_for_status()


def is_valid_signature(raw_body: bytes, header: str) -> bool:
    """Check X-Hub-Signature-256: 'sha256=' + HMAC-SHA256 of the raw body keyed with the App Secret."""
    secret = get_settings().meta_app_secret
    if not secret:
        logger.error("META_APP_SECRET is not set; rejecting webhook call")
        return False
    expected = "sha256=" + hmac.new(secret.encode(), raw_body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected.encode(), header.encode())


def download_media(media_id: str) -> bytes:
    """Two steps: ask Graph for the file's temporary URL, then fetch it. Both need the access token."""
    with _client() as client:
        info_response = client.get(_graph_url(media_id), headers=_auth_header())
        _check(info_response)
        info = info_response.json()
        if int(info.get("file_size") or 0) > MAX_MEDIA_BYTES:
            raise MediaTooLarge()

        chunks, total = [], 0
        headers = {**_auth_header(), "User-Agent": USER_AGENT}
        with client.stream("GET", info["url"], headers=headers) as response:
            _check(response)
            for chunk in response.iter_bytes():
                total += len(chunk)
                if total > MAX_MEDIA_BYTES:
                    raise MediaTooLarge()
                chunks.append(chunk)
        return b"".join(chunks)


def send_text(phone_number_id: str, recipient: str, body: str, reply_to: str | None = None) -> None:
    """Send a plain text reply. Free-form text is allowed within 24h of the user's last message."""
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "type": "text",
        "text": {"body": body[:4096]},
    }
    # Normally the webhook gives a phone number (digits only). Users with a WhatsApp username may only
    # have a business-scoped ID like "US.1349...", which Meta wants in "recipient" instead of "to".
    payload["to" if recipient.isdigit() else "recipient"] = recipient
    if reply_to:
        payload["context"] = {"message_id": reply_to}
    with _client() as client:
        _check(client.post(_graph_url(f"{phone_number_id}/messages"), headers=_auth_header(), json=payload))
