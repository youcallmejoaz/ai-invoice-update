import asyncio
import hashlib
import hmac
import json

import pytest
from fastapi.testclient import TestClient

from app import extractor, main, sheets, whatsapp
from app.config import get_settings
from app.models import Invoice

SECRET = "app-secret"
VERIFY_TOKEN = "verify-me"
SENDER = "15551234567"
PHONE_NUMBER_ID = "PNID1"
PDF_BYTES = b"%PDF-1.4 fake invoice"


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", SECRET)
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", VERIFY_TOKEN)
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "token")
    get_settings.cache_clear()
    main._seen.clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def fakes(monkeypatch):
    calls = {"sent": [], "saved": [], "downloaded": []}
    invoice = Invoice(invoice_number="INV-9", supplier_name="Acme", currency="USD", subtotal=100, tax=10, total=110)

    def download(media_id):
        calls["downloaded"].append(media_id)
        return PDF_BYTES

    monkeypatch.setattr(whatsapp, "download_media", download)
    monkeypatch.setattr(extractor, "extract_invoice", lambda data, mime: invoice)
    monkeypatch.setattr(sheets, "append_invoice", lambda inv, sender, at: calls["saved"].append((inv, sender)))
    monkeypatch.setattr(
        whatsapp, "send_text",
        lambda pnid, to, body, reply_to=None: calls["sent"].append((pnid, to, body, reply_to)),
    )
    return calls


client = TestClient(main.app)


def envelope(messages=None, statuses=None, phone_number_id=PHONE_NUMBER_ID, field="messages"):
    value = {
        "messaging_product": "whatsapp",
        "metadata": {"display_phone_number": "15550001111", "phone_number_id": phone_number_id},
    }
    if messages is not None:
        value["messages"] = messages
        value["contacts"] = [{"profile": {"name": "Ann"}, "wa_id": SENDER}]
    if statuses is not None:
        value["statuses"] = statuses
    return {
        "object": "whatsapp_business_account",
        "entry": [{"id": "WABA", "changes": [{"field": field, "value": value}]}],
    }


def document(msg_id="wamid.1", media_id="MEDIA1", mime="application/pdf"):
    return {
        "from": SENDER, "id": msg_id, "timestamp": "1700000000", "type": "document",
        "document": {"id": media_id, "mime_type": mime, "filename": "invoice.pdf", "sha256": "x"},
    }


def sign(body: bytes, secret=SECRET) -> str:
    return "sha256=" + hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def post(payload, signature=None, secret=SECRET):
    body = payload if isinstance(payload, bytes) else json.dumps(payload).encode()
    headers = {"Content-Type": "application/json"}
    headers["X-Hub-Signature-256"] = signature if signature is not None else sign(body, secret)
    return client.post("/whatsapp/webhook", content=body, headers=headers)


# --- GET: Meta's verification handshake ---

def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_verification_echoes_the_challenge_as_plain_text():
    response = client.get(
        "/whatsapp/webhook",
        params={"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1158201444"},
    )
    assert response.status_code == 200
    assert response.text == "1158201444"  # bare, not a JSON string with quotes


@pytest.mark.parametrize("params", [
    {"hub.mode": "subscribe", "hub.verify_token": "wrong", "hub.challenge": "1"},
    {"hub.mode": "unsubscribe", "hub.verify_token": VERIFY_TOKEN, "hub.challenge": "1"},
    {"hub.mode": "subscribe", "hub.verify_token": VERIFY_TOKEN},
    {},
])
def test_verification_rejects_bad_requests(params):
    assert client.get("/whatsapp/webhook", params=params).status_code == 403


def test_verification_fails_closed_when_no_verify_token_is_configured(monkeypatch):
    monkeypatch.setenv("WHATSAPP_VERIFY_TOKEN", "")
    get_settings.cache_clear()
    response = client.get("/whatsapp/webhook", params={"hub.mode": "subscribe", "hub.verify_token": "", "hub.challenge": "1"})
    assert response.status_code == 403


# --- POST: signature ---

def test_bad_signature_is_rejected(fakes):
    assert post(envelope([document()]), secret="someone-else").status_code == 403
    assert fakes["saved"] == [] and fakes["sent"] == []


def test_missing_or_malformed_signature_is_rejected(fakes):
    body = json.dumps(envelope([document()])).encode()
    assert client.post("/whatsapp/webhook", content=body).status_code == 403
    assert post(body, signature="sha1=abc").status_code == 403
    assert post(body, signature=b"sha256=\xe9").status_code == 403  # non-ASCII bytes must not crash the check
    assert client.post("/whatsapp/webhook", content=b"x" * (main.MAX_BODY_BYTES + 1)).status_code == 403


def test_tampered_body_is_rejected(fakes):
    good = json.dumps(envelope([document()])).encode()
    assert post(good.replace(b"MEDIA1", b"MEDIA2"), signature=sign(good)).status_code == 403


def test_unconfigured_app_secret_fails_closed(fakes, monkeypatch):
    monkeypatch.setenv("META_APP_SECRET", "")
    get_settings.cache_clear()
    body = json.dumps(envelope([document()])).encode()
    assert post(body, signature=sign(body, secret="")).status_code == 403
    assert fakes["saved"] == []


def test_signed_but_non_json_body_is_a_400():
    assert post(b"not json").status_code == 400


# --- POST: messages ---

def test_pdf_is_downloaded_saved_and_confirmed(fakes):
    assert post(envelope([document()])).status_code == 200

    assert fakes["downloaded"] == ["MEDIA1"]
    (saved_invoice, sender), = fakes["saved"]
    assert saved_invoice.invoice_number == "INV-9"
    assert sender == SENDER

    ack, confirmation = fakes["sent"]
    assert ack[:2] == (PHONE_NUMBER_ID, SENDER) and "Reading your invoice" in ack[2]
    assert confirmation[3] == "wamid.1"  # replies quote the invoice message
    assert "INV-9" in confirmation[2] and "Acme" in confirmation[2] and "110" in confirmation[2]
    assert "Please check" not in confirmation[2]


def test_warnings_are_included_in_the_reply(fakes, monkeypatch):
    bad = Invoice(invoice_number="INV-9", subtotal=100, tax=10, total=999)
    monkeypatch.setattr(extractor, "extract_invoice", lambda data, mime: bad)
    post(envelope([document()]))
    assert "Please check" in fakes["sent"][-1][2]


def test_photo_message_is_accepted(fakes):
    image = {"from": SENDER, "id": "wamid.img", "type": "image", "image": {"id": "IMG1", "mime_type": "image/jpeg"}}
    post(envelope([image]))
    assert fakes["downloaded"] == ["IMG1"]


def test_text_message_gets_instructions_and_no_processing(fakes):
    text = {"from": SENDER, "id": "wamid.t", "type": "text", "text": {"body": "hi"}}
    post(envelope([text]))
    assert fakes["downloaded"] == [] and fakes["saved"] == []
    assert "Send me an invoice" in fakes["sent"][0][2]


def test_unsupported_file_is_rejected_by_content_not_by_declared_type(fakes, monkeypatch):
    monkeypatch.setattr(whatsapp, "download_media", lambda media_id: b"PK\x03\x04 a zip file")
    post(envelope([document(mime="application/pdf")]))  # claims to be a PDF, is not
    assert fakes["saved"] == []
    assert "PDF, JPG, PNG or WebP" in fakes["sent"][-1][2]


def test_pdf_declared_as_octet_stream_is_still_processed(fakes):
    post(envelope([document(mime="application/octet-stream")]))
    assert len(fakes["saved"]) == 1


def test_oversized_file_gets_a_friendly_error(fakes, monkeypatch):
    def too_big(media_id):
        raise whatsapp.MediaTooLarge()

    monkeypatch.setattr(whatsapp, "download_media", too_big)
    post(envelope([document()]))
    assert "too large" in fakes["sent"][-1][2]


def test_failure_sends_a_friendly_error(fakes, monkeypatch):
    def boom(data, mime):
        raise RuntimeError("gemini down")

    monkeypatch.setattr(extractor, "extract_invoice", boom)
    assert post(envelope([document()])).status_code == 200  # still 200, or Meta would retry
    assert fakes["saved"] == []
    assert "couldn't read that invoice" in fakes["sent"][-1][2]


def test_a_failing_reply_does_not_break_processing(fakes, monkeypatch):
    def broken_send(*args, **kwargs):
        raise RuntimeError("131030 recipient not in allowed list")

    monkeypatch.setattr(whatsapp, "send_text", broken_send)
    assert post(envelope([document()])).status_code == 200
    assert len(fakes["saved"]) == 1  # the invoice is still saved


def test_duplicate_delivery_is_processed_once(fakes):
    payload = envelope([document(msg_id="wamid.dup")])
    post(payload)
    post(payload)
    assert len(fakes["saved"]) == 1


def test_batched_messages_across_entries_and_changes(fakes):
    payload = envelope([document("wamid.a", "MEDIA_A"), document("wamid.b", "MEDIA_B")])
    second = envelope([document("wamid.c", "MEDIA_C")])
    payload["entry"].extend(second["entry"])
    post(payload)
    assert sorted(fakes["downloaded"]) == ["MEDIA_A", "MEDIA_B", "MEDIA_C"]


def test_status_updates_are_acknowledged_and_ignored(fakes):
    statuses = [{"id": "wamid.out", "status": "delivered", "timestamp": "1", "recipient_id": SENDER}]
    assert post(envelope(statuses=statuses)).status_code == 200
    assert fakes["sent"] == [] and fakes["saved"] == []


def test_failed_status_is_logged(fakes, caplog):
    statuses = [{"id": "wamid.out", "status": "failed", "errors": [{"code": 131030, "title": "not allowed"}]}]
    post(envelope(statuses=statuses))
    assert "131030" in caplog.text


def test_other_webhook_fields_are_ignored(fakes):
    assert post(envelope([document()], field="account_update")).status_code == 200
    assert fakes["downloaded"] == []


@pytest.mark.parametrize("payload", [{}, {"entry": "nope"}, {"entry": [{"changes": None}]}, []])
def test_odd_payloads_are_acknowledged(payload, fakes):
    assert post(payload).status_code == 200


def test_sender_without_phone_number_falls_back_to_scoped_id(fakes):
    message = {"id": "wamid.u", "type": "document", "from_user_id": "US.1349", "document": {"id": "M1"}}
    post(envelope([message]))
    assert fakes["sent"][0][1] == "US.1349"


# --- POST: raw-body signature, body cap, ordering ---

def test_signature_is_checked_over_the_raw_bytes_not_a_re_serialised_copy(fakes):
    # Meta's bodies are compact and escape "/" as "\/" and non-ASCII as \uXXXX; json.dumps would not
    # reproduce them byte for byte, so verifying a re-serialised copy would reject every real webhook.
    raw = (
        '{"object":"whatsapp_business_account","entry":[{"id":"W","changes":[{"field":"messages","value":'
        '{"metadata":{"phone_number_id":"PNID1"},"messages":[{"from":"15551234567","id":"wamid.raw",'
        '"type":"document","document":{"id":"M\\/1","filename":"caf\\u00e9.pdf"}}]}}]}]}'
    ).encode()
    assert json.dumps(json.loads(raw)).encode() != raw  # sanity: re-serialising really changes the bytes
    assert post(raw).status_code == 200
    assert fakes["downloaded"] == ["M/1"]


def test_oversized_body_is_rejected_before_it_is_read(fakes):
    headers = {"X-Hub-Signature-256": "sha256=" + "0" * 64}
    response = client.post("/whatsapp/webhook", content=b"x" * (main.MAX_BODY_BYTES + 1), headers=headers)
    assert response.status_code == 413


def test_chunked_body_over_the_cap_is_rejected(fakes):
    mib = 1024 * 1024
    chunks = (b"x" * mib for _ in range(main.MAX_BODY_BYTES // mib + 2))  # no Content-Length is sent
    headers = {"X-Hub-Signature-256": "sha256=" + "0" * 64}
    assert client.post("/whatsapp/webhook", content=chunks, headers=headers).status_code == 413


def test_response_is_sent_before_the_work_starts(fakes, monkeypatch):
    # TestClient runs background tasks before it returns, so drive the ASGI app directly to see the order.
    events = []
    monkeypatch.setattr(main, "handle_message", lambda *args, **kwargs: events.append("work"))
    body = json.dumps(envelope([document()])).encode()
    scope = {
        "type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "POST",
        "path": "/whatsapp/webhook", "raw_path": b"/whatsapp/webhook", "query_string": b"", "root_path": "",
        "scheme": "http", "server": ("testserver", 80), "client": ("testclient", 5000),
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode()),
            (b"x-hub-signature-256", sign(body).encode()),
        ],
    }

    async def run():
        delivered = False

        async def receive():
            nonlocal delivered
            if not delivered:
                delivered = True
                return {"type": "http.request", "body": body, "more_body": False}
            return {"type": "http.disconnect"}

        async def send(message):
            if message["type"] == "http.response.body" and not message.get("more_body"):
                events.append("response-sent")

        await main.app(scope, receive, send)

    asyncio.run(run())
    assert events == ["response-sent", "work"]


# --- POST: message kinds and envelope shapes ---

def test_reactions_and_system_messages_are_ignored_silently(fakes):
    reaction = {"from": SENDER, "id": "wamid.r", "type": "reaction", "reaction": {"message_id": "wamid.1", "emoji": "👍"}}
    system = {"from": SENDER, "id": "wamid.s", "type": "system", "system": {"body": "user changed number"}}
    assert post(envelope([reaction, system])).status_code == 200
    assert fakes["sent"] == [] and fakes["downloaded"] == []


def test_two_changes_in_one_entry_are_both_processed(fakes):
    payload = envelope([document("wamid.a", "MEDIA_A")])
    payload["entry"][0]["changes"].extend(envelope([document("wamid.b", "MEDIA_B")])["entry"][0]["changes"])
    post(payload)
    assert sorted(fakes["downloaded"]) == ["MEDIA_A", "MEDIA_B"]


def test_sender_falls_back_to_the_contacts_user_id(fakes):
    message = {"id": "wamid.c", "type": "document", "document": {"id": "M1"}}  # no "from", no "from_user_id"
    payload = envelope([message])
    payload["entry"][0]["changes"][0]["value"]["contacts"] = [{"profile": {"name": "Ann"}, "user_id": "US.2222"}]
    post(payload)
    assert fakes["sent"][0][1] == "US.2222"
