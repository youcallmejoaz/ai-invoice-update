from types import SimpleNamespace

import pytest

from app import extractor
from app.config import get_settings
from app.extractor import sniff_mime
from app.models import Invoice


@pytest.mark.parametrize("data, expected", [
    (b"%PDF-1.7\n...", "application/pdf"),
    (b"\n\n  %PDF-1.4", "application/pdf"),  # a few stray bytes before the header are allowed
    (b"\x89PNG\r\n\x1a\n....", "image/png"),
    (b"\xff\xd8\xff\xe0....", "image/jpeg"),
    (b"RIFF\x00\x00\x00\x00WEBPVP8 ", "image/webp"),
    (b"PK\x03\x04 zip", None),
    (b"RIFF\x00\x00\x00\x00WAVEfmt ", None),  # a RIFF file that is not WebP
    (b"\x89PNG", None),  # signature cut short
    (b"\xff\xd8", None),
    pytest.param(b"x" * 1030 + b"%PDF", None, id="pdf-marker-too-far-in"),  # %PDF only counts near the start
    (b"", None),
])
def test_sniff_mime(data, expected):
    assert sniff_mime(data) == expected


class FakeGemini:
    """Stands in for google.genai.Client: records what extract_invoice sends and returns a canned reply."""

    def __init__(self, parsed):
        self.parsed = parsed
        self.calls = []
        self.api_keys = []

    def client(self, api_key=None):
        self.api_keys.append(api_key)
        return SimpleNamespace(models=SimpleNamespace(generate_content=self.generate_content))

    def generate_content(self, model, contents, config):
        self.calls.append({"model": model, "contents": contents, "config": config})
        return SimpleNamespace(parsed=self.parsed)


@pytest.fixture
def gemini_env(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.setenv("GEMINI_MODEL", "test-model")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_extract_invoice_sends_the_file_prompt_and_schema_to_gemini(monkeypatch, gemini_env):
    invoice = Invoice(invoice_number="INV-1", total=10)
    fake = FakeGemini(invoice)
    monkeypatch.setattr(extractor.genai, "Client", fake.client)

    assert extractor.extract_invoice(b"%PDF-1.4 bytes", "application/pdf") is invoice

    assert fake.api_keys == ["test-key"]
    (call,) = fake.calls
    assert call["model"] == "test-model"
    part, prompt = call["contents"]
    assert part.inline_data.data == b"%PDF-1.4 bytes" and part.inline_data.mime_type == "application/pdf"
    assert prompt == extractor.PROMPT
    assert call["config"].response_mime_type == "application/json"
    assert call["config"].response_schema is Invoice
    assert call["config"].temperature == 0


@pytest.mark.parametrize("parsed", [None, {"invoice_number": "INV-1"}])
def test_extract_invoice_rejects_a_reply_that_is_not_a_valid_invoice(monkeypatch, gemini_env, parsed):
    monkeypatch.setattr(extractor.genai, "Client", FakeGemini(parsed).client)
    with pytest.raises(ValueError):
        extractor.extract_invoice(b"%PDF-1.4", "application/pdf")
