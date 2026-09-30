"""Generate a fake invoice with known values: python scripts/make_sample_invoice.py"""
from pathlib import Path

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parent.parent / "samples" / "sample_invoice.pdf"

ITEMS = [
    ("Web design services", 10, 150.00),
    ("Hosting (12 months)", 12, 25.00),
    ("Domain registration", 1, 15.00),
]
TAX_RATE = 0.10


def main() -> None:
    OUT.parent.mkdir(exist_ok=True)
    pdf = canvas.Canvas(str(OUT), pagesize=A4)
    _, height = A4
    y = height - 25 * mm

    pdf.setFont("Helvetica-Bold", 20)
    pdf.drawString(20 * mm, y, "INVOICE")
    pdf.setFont("Helvetica", 11)
    for line in [
        "Acme Web Studio Ltd", "12 Example Street, London", "Tax ID: GB123456789", "",
        "Invoice No: INV-2026-0042", "Invoice Date: 15 September 2026", "Due Date: 15 October 2026", "",
        "Bill to: Globex Corporation", "Currency: USD",
    ]:
        y -= 6 * mm
        pdf.drawString(20 * mm, y, line)

    y -= 14 * mm
    pdf.setFont("Helvetica-Bold", 11)
    for x, label in [(20, "Description"), (100, "Qty"), (125, "Unit price"), (160, "Amount")]:
        pdf.drawString(x * mm, y, label)
    pdf.setFont("Helvetica", 11)

    subtotal = 0.0
    for description, qty, price in ITEMS:
        amount = qty * price
        subtotal += amount
        y -= 7 * mm
        pdf.drawString(20 * mm, y, description)
        pdf.drawString(100 * mm, y, str(qty))
        pdf.drawString(125 * mm, y, f"{price:,.2f}")
        pdf.drawString(160 * mm, y, f"{amount:,.2f}")

    tax = round(subtotal * TAX_RATE, 2)
    y -= 14 * mm
    for label, value in [("Subtotal", subtotal), ("Tax (10%)", tax), ("TOTAL", subtotal + tax)]:
        pdf.drawString(125 * mm, y, label)
        pdf.drawString(160 * mm, y, f"{value:,.2f}")
        y -= 7 * mm

    pdf.save()
    print(f"Wrote {OUT} (subtotal {subtotal:,.2f}, tax {tax:,.2f}, total {subtotal + tax:,.2f})")


if __name__ == "__main__":
    main()
