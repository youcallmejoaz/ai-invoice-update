import httpx
from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.config import get_settings


def is_valid_signature(url: str, form: dict, signature: str) -> bool:
    return RequestValidator(get_settings().twilio_auth_token).validate(url, form, signature)


def download_media(url: str) -> bytes:
    """Fetch a file Twilio received from WhatsApp. Twilio requires basic auth with SID/token."""
    settings = get_settings()
    response = httpx.get(
        url,
        auth=(settings.twilio_account_sid, settings.twilio_auth_token),
        follow_redirects=True,
        timeout=30,
    )
    response.raise_for_status()
    return response.content


def send_whatsapp(to: str, body: str) -> None:
    settings = get_settings()
    Client(settings.twilio_account_sid, settings.twilio_auth_token).messages.create(
        from_=settings.twilio_whatsapp_from, to=to, body=body
    )
