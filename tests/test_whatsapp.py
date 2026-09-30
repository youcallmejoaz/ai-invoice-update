import hashlib
import hmac

import httpx
import pytest

from app import whatsapp
from app.config import get_settings


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("WHATSAPP_ACCESS_TOKEN", "tok")
    monkeypatch.setenv("GRAPH_API_VERSION", "v26.0")
    monkeypatch.setenv("META_APP_SECRET", "secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def use_transport(monkeypatch, handler):
    monkeypatch.setattr(
        whatsapp, "_client",
        lambda: httpx.Client(transport=httpx.MockTransport(handler), follow_redirects=True),
    )


def test_download_uses_the_two_step_flow_with_the_token_each_time(monkeypatch):
    seen = []

    def handler(request):
        seen.append((request.url.host, request.url.path, request.headers.get("authorization")))
        if request.url.host == "graph.facebook.com":
            return httpx.Response(200, json={
                "url": "https://lookaside.fbsbx.com/whatsapp_business/attachments/?mid=1",
                "file_size": "10", "mime_type": "application/pdf", "id": "MEDIA1",
            })
        assert request.headers["user-agent"] == whatsapp.USER_AGENT
        return httpx.Response(200, content=b"%PDF-bytes")

    use_transport(monkeypatch, handler)
    assert whatsapp.download_media("MEDIA1") == b"%PDF-bytes"
    assert seen == [
        ("graph.facebook.com", "/v26.0/MEDIA1", "Bearer tok"),
        ("lookaside.fbsbx.com", "/whatsapp_business/attachments/", "Bearer tok"),
    ]


def test_download_refuses_a_declared_oversize_file_without_fetching_it(monkeypatch):
    hosts = []

    def handler(request):
        hosts.append(request.url.host)
        return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/x", "file_size": str(50 * 1024 * 1024)})

    use_transport(monkeypatch, handler)
    with pytest.raises(whatsapp.MediaTooLarge):
        whatsapp.download_media("MEDIA1")
    assert hosts == ["graph.facebook.com"]


def test_download_stops_at_the_cap_even_if_file_size_was_missing(monkeypatch):
    monkeypatch.setattr(whatsapp, "MAX_MEDIA_BYTES", 10)

    def handler(request):
        if request.url.host == "graph.facebook.com":
            return httpx.Response(200, json={"url": "https://lookaside.fbsbx.com/x"})
        return httpx.Response(200, content=b"x" * 100)

    use_transport(monkeypatch, handler)
    with pytest.raises(whatsapp.MediaTooLarge):
        whatsapp.download_media("MEDIA1")


def test_download_error_is_raised_and_logged(monkeypatch, caplog):
    use_transport(monkeypatch, lambda request: httpx.Response(400, json={"error": {"code": 100, "error_subcode": 33}}))
    with pytest.raises(httpx.HTTPStatusError):
        whatsapp.download_media("MEDIA1")
    assert "error_subcode" in caplog.text
    assert "tok" not in caplog.text  # never log the access token


def sent_request(monkeypatch, **kwargs):
    captured = {}

    def handler(request):
        captured["url"] = str(request.url)
        captured["auth"] = request.headers["authorization"]
        captured["json"] = __import__("json").loads(request.content)
        return httpx.Response(200, json={"messages": [{"id": "wamid.out"}]})

    use_transport(monkeypatch, handler)
    whatsapp.send_text("PNID1", **kwargs)
    return captured


def test_send_text_to_a_phone_number(monkeypatch):
    sent = sent_request(monkeypatch, recipient="15551234567", body="hello", reply_to="wamid.in")
    assert sent["url"] == "https://graph.facebook.com/v26.0/PNID1/messages"
    assert sent["auth"] == "Bearer tok"
    assert sent["json"] == {
        "messaging_product": "whatsapp", "recipient_type": "individual", "type": "text",
        "text": {"body": "hello"}, "to": "15551234567", "context": {"message_id": "wamid.in"},
    }


def test_send_text_to_a_scoped_user_id_uses_recipient(monkeypatch):
    sent = sent_request(monkeypatch, recipient="US.1349", body="hi")
    assert sent["json"]["recipient"] == "US.1349" and "to" not in sent["json"]
    assert "context" not in sent["json"]


def test_send_text_truncates_to_the_4096_char_limit(monkeypatch):
    sent = sent_request(monkeypatch, recipient="1555", body="x" * 5000)
    assert len(sent["json"]["text"]["body"]) == 4096


def test_send_text_raises_on_meta_errors(monkeypatch):
    use_transport(monkeypatch, lambda request: httpx.Response(400, json={"error": {"code": 131030}}))
    with pytest.raises(httpx.HTTPStatusError):
        whatsapp.send_text("PNID1", "1555", "hi")


def test_signature_check():
    body = b'{"a": 1}'
    good = "sha256=" + hmac.new(b"secret", body, hashlib.sha256).hexdigest()
    assert whatsapp.is_valid_signature(body, good)
    assert not whatsapp.is_valid_signature(body, good[:-1] + "0")
    assert not whatsapp.is_valid_signature(body, "")
    assert not whatsapp.is_valid_signature(b'{"a": 2}', good)
