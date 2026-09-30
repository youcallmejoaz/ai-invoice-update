import pytest
from fastapi.testclient import TestClient
from twilio.request_validator import RequestValidator

from app import extractor, main, sheets, whatsapp
from app.config import get_settings
from app.models import Invoice

PDF_FORM = {
    "From": "whatsapp:+15551234567",
    "NumMedia": "1",
    "MediaUrl0": "https://api.twilio.com/media/ME123",
    "MediaContentType0": "application/pdf",
}


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "")
    monkeypatch.setenv("TWILIO_AUTH_TOKEN", "test-token")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fakes(monkeypatch):
    calls = {"sent": [], "saved": []}
    invoice = Invoice(invoice_number="INV-9", supplier_name="Acme", currency="USD", subtotal=100, tax=10, total=110)
    monkeypatch.setattr(whatsapp, "download_media", lambda url: b"%PDF-fake")
    monkeypatch.setattr(extractor, "extract_invoice", lambda data, mime: invoice)
    monkeypatch.setattr(sheets, "append_invoice", lambda inv, sender, at: calls["saved"].append((inv, sender)))
    monkeypatch.setattr(whatsapp, "send_whatsapp", lambda to, body: calls["sent"].append((to, body)))
    return calls


client = TestClient(main.app)


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_message_without_attachment_asks_for_a_pdf(fakes):
    response = client.post("/whatsapp/webhook", data={"From": "whatsapp:+1555", "NumMedia": "0", "Body": "hi"})
    assert response.status_code == 200
    assert "Send me an invoice" in response.text
    assert fakes["saved"] == []


def test_unsupported_file_type_is_rejected(fakes):
    response = client.post("/whatsapp/webhook", data={**PDF_FORM, "MediaContentType0": "audio/ogg"})
    assert "PDF, JPG, PNG or WebP" in response.text
    assert fakes["saved"] == []


def test_pdf_is_processed_saved_and_confirmed(fakes):
    response = client.post("/whatsapp/webhook", data=PDF_FORM)
    assert "Reading your invoice" in response.text

    (saved_invoice, sender), = fakes["saved"]
    assert saved_invoice.invoice_number == "INV-9"
    assert sender == "whatsapp:+15551234567"
    (to, body), = fakes["sent"]
    assert to == "whatsapp:+15551234567"
    assert "INV-9" in body and "Acme" in body and "110" in body
    assert "Please check" not in body


def test_warnings_are_included_in_the_reply(fakes, monkeypatch):
    bad = Invoice(invoice_number="INV-9", subtotal=100, tax=10, total=999)
    monkeypatch.setattr(extractor, "extract_invoice", lambda data, mime: bad)
    client.post("/whatsapp/webhook", data=PDF_FORM)
    assert "Please check" in fakes["sent"][0][1]


def test_failure_sends_a_friendly_error(fakes, monkeypatch):
    def boom(data, mime):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(extractor, "extract_invoice", boom)
    client.post("/whatsapp/webhook", data=PDF_FORM)
    assert fakes["saved"] == []
    assert "couldn't read that invoice" in fakes["sent"][0][1]


def test_bad_signature_is_rejected_and_good_one_accepted(fakes, monkeypatch):
    monkeypatch.setenv("PUBLIC_BASE_URL", "https://example.ngrok.app")
    get_settings.cache_clear()
    url = "https://example.ngrok.app/whatsapp/webhook"

    bad = client.post("/whatsapp/webhook", data=PDF_FORM, headers={"X-Twilio-Signature": "nope"})
    assert bad.status_code == 403
    assert fakes["saved"] == []

    signature = RequestValidator("test-token").compute_signature(url, PDF_FORM)
    good = client.post("/whatsapp/webhook", data=PDF_FORM, headers={"X-Twilio-Signature": signature})
    assert good.status_code == 200
    assert len(fakes["saved"]) == 1
