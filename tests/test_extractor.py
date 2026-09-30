import pytest

from app.extractor import sniff_mime


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
    (b"x" * 1030 + b"%PDF", None),  # %PDF only counts near the start
    (b"", None),
])
def test_sniff_mime(data, expected):
    assert sniff_mime(data) == expected
