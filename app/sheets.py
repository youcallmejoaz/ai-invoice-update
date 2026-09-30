from datetime import datetime

import gspread

from app.config import get_settings
from app.models import Invoice

INVOICE_HEADERS = [
    "Received At", "From", "Invoice Number", "Invoice Date", "Due Date", "Supplier",
    "Supplier Tax ID", "Customer", "Currency", "Subtotal", "Tax", "Total",
    "# Line Items", "Warnings",
]
LINE_ITEM_HEADERS = ["Invoice Number", "Description", "Quantity", "Unit Price", "Amount"]


def _get_or_create(spreadsheet, title: str, headers: list[str]):
    try:
        worksheet = spreadsheet.worksheet(title)
    except gspread.WorksheetNotFound:
        worksheet = spreadsheet.add_worksheet(title=title, rows=1000, cols=len(headers))
    if not worksheet.row_values(1):
        worksheet.append_row(headers)
    return worksheet


def _cell(value):
    return "" if value is None else value


def append_invoice(invoice: Invoice, sender: str, received_at: datetime) -> None:
    """Append one row to the Invoices tab and one row per line item to the LineItems tab."""
    settings = get_settings()
    client = gspread.service_account(filename=settings.google_service_account_file)
    spreadsheet = client.open_by_key(settings.google_sheet_id)
    invoices = _get_or_create(spreadsheet, "Invoices", INVOICE_HEADERS)
    line_items = _get_or_create(spreadsheet, "LineItems", LINE_ITEM_HEADERS)

    # RAW, not USER_ENTERED: text from an invoice must never be interpreted as a spreadsheet formula.
    invoices.append_row(
        [
            received_at.isoformat(timespec="seconds"),
            sender,
            _cell(invoice.invoice_number),
            _cell(invoice.invoice_date),
            _cell(invoice.due_date),
            _cell(invoice.supplier_name),
            _cell(invoice.supplier_tax_id),
            _cell(invoice.customer_name),
            _cell(invoice.currency),
            _cell(invoice.subtotal),
            _cell(invoice.tax),
            _cell(invoice.total),
            len(invoice.line_items),
            "; ".join(invoice.warnings()),
        ],
        value_input_option="RAW",
    )
    if invoice.line_items:
        line_items.append_rows(
            [
                [
                    _cell(invoice.invoice_number),
                    _cell(item.description),
                    _cell(item.quantity),
                    _cell(item.unit_price),
                    _cell(item.amount),
                ]
                for item in invoice.line_items
            ],
            value_input_option="RAW",
        )
