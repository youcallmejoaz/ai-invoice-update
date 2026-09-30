from google import genai
from google.genai import types

from app.config import get_settings
from app.models import Invoice

PROMPT = (
    "Extract the invoice data from this document. "
    "Use null for anything that is not printed on the invoice; never guess. "
    "Dates must be YYYY-MM-DD. Amounts must be plain numbers without currency symbols "
    "or thousands separators. Include every line item."
)


def sniff_mime(data: bytes) -> str | None:
    """Identify a supported file from its first bytes. The MIME type WhatsApp reports is not reliable."""
    if b"%PDF" in data[:1024]:
        return "application/pdf"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "image/png"
    if data.startswith(b"\xff\xd8\xff"):
        return "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp"
    return None


def extract_invoice(data: bytes, mime_type: str) -> Invoice:
    """Send an invoice PDF or image to Gemini and get back a validated Invoice."""
    client = genai.Client(api_key=get_settings().gemini_api_key)
    response = client.models.generate_content(
        model=get_settings().gemini_model,
        contents=[types.Part.from_bytes(data=data, mime_type=mime_type), PROMPT],
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=Invoice,
            temperature=0,
        ),
    )
    if not isinstance(response.parsed, Invoice):
        raise ValueError("Gemini did not return a valid invoice")
    return response.parsed
