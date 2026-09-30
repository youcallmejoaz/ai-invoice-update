"""Try the extraction without WhatsApp: python -m app.cli samples/sample_invoice.pdf [--sheet]"""
import argparse
import mimetypes
from datetime import datetime, timezone
from pathlib import Path

from app.extractor import extract_invoice
from app.sheets import append_invoice


def main() -> None:
    parser = argparse.ArgumentParser(description="Extract invoice data with Gemini")
    parser.add_argument("file", type=Path, help="invoice PDF or image")
    parser.add_argument("--sheet", action="store_true", help="also append the result to the Google Sheet")
    args = parser.parse_args()

    mime_type = mimetypes.guess_type(args.file.name)[0] or "application/pdf"
    invoice = extract_invoice(args.file.read_bytes(), mime_type)
    print(invoice.model_dump_json(indent=2))
    for warning in invoice.warnings():
        print(f"WARNING: {warning}")
    if args.sheet:
        append_invoice(invoice, "cli", datetime.now(timezone.utc))
        print("Appended to Google Sheet.")


if __name__ == "__main__":
    main()
