"""Try the extraction without WhatsApp: python -m app.cli samples/sample_invoice.pdf [--sheet]"""
import argparse
from datetime import datetime, timezone
from pathlib import Path

from app.extractor import extract_invoice, sniff_mime
from app.sheets import append_invoice


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract invoice data with Gemini")
    parser.add_argument("file", type=Path, help="invoice PDF or image")
    parser.add_argument("--sheet", action="store_true", help="also append the result to the Google Sheet")
    args = parser.parse_args()

    data = args.file.read_bytes()
    mime_type = sniff_mime(data)
    if not mime_type:
        parser.error("unsupported file: use a PDF, JPG, PNG or WebP")
    invoice = extract_invoice(data, mime_type)
    print(invoice.model_dump_json(indent=2))
    for warning in invoice.warnings():
        print(f"WARNING: {warning}")
    if args.sheet:
        append_invoice(invoice, "cli", datetime.now(timezone.utc))
        print("Appended to Google Sheet.")


if __name__ == "__main__":
    main()
