from datetime import datetime, timezone

import gspread
import pytest

from app import sheets
from app.config import get_settings
from app.models import Invoice, LineItem


class FakeWorksheet:
    def __init__(self):
        self.rows = []
        self.kwargs = []

    def row_values(self, index):
        return self.rows[index - 1] if self.rows else []

    def append_row(self, values, **kwargs):
        self.rows.append(values)
        self.kwargs.append(kwargs)

    def append_rows(self, rows, **kwargs):
        self.rows.extend(rows)
        self.kwargs.append(kwargs)


class FakeSpreadsheet:
    def __init__(self):
        self.tabs = {}

    def worksheet(self, title):
        if title not in self.tabs:
            raise gspread.WorksheetNotFound(title)
        return self.tabs[title]

    def add_worksheet(self, title, rows, cols):
        self.tabs[title] = FakeWorksheet()
        return self.tabs[title]


@pytest.fixture
def spreadsheet(monkeypatch):
    monkeypatch.setenv("GOOGLE_SHEET_ID", "sheet-id")
    get_settings.cache_clear()
    fake = FakeSpreadsheet()

    class FakeClient:
        def open_by_key(self, key):
            assert key == "sheet-id"
            return fake

    monkeypatch.setattr(sheets.gspread, "service_account", lambda filename: FakeClient())
    yield fake
    get_settings.cache_clear()


def test_creates_tabs_with_headers_and_appends_rows(spreadsheet):
    invoice = Invoice(
        invoice_number="INV-1", supplier_name="Acme", currency="USD", subtotal=100, tax=10, total=110,
        line_items=[LineItem(description="Widget", quantity=2, unit_price=50, amount=100)],
    )
    sheets.append_invoice(invoice, "15551234567", datetime(2026, 9, 30, 12, 0, tzinfo=timezone.utc))

    invoices = spreadsheet.tabs["Invoices"].rows
    assert invoices[0] == sheets.INVOICE_HEADERS
    row = dict(zip(sheets.INVOICE_HEADERS, invoices[1]))
    assert row["Received At"] == "2026-09-30T12:00:00+00:00"
    assert row["From"] == "15551234567"
    assert row["Invoice Number"] == "INV-1"
    assert row["Total"] == 110
    assert row["# Line Items"] == 1
    assert row["Due Date"] == ""  # missing values become empty cells, not "None"

    items = spreadsheet.tabs["LineItems"].rows
    assert items == [sheets.LINE_ITEM_HEADERS, ["INV-1", "Widget", 2, 50, 100]]


def test_headers_are_written_only_once(spreadsheet):
    invoice = Invoice(invoice_number="INV-1", total=1)
    now = datetime.now(timezone.utc)
    sheets.append_invoice(invoice, "a", now)
    sheets.append_invoice(invoice, "b", now)
    rows = spreadsheet.tabs["Invoices"].rows
    assert len(rows) == 3
    assert rows[0] == sheets.INVOICE_HEADERS


def test_values_are_written_raw_so_text_cannot_become_a_formula(spreadsheet):
    sheets.append_invoice(Invoice(invoice_number="=1+1"), "a", datetime.now(timezone.utc))
    assert spreadsheet.tabs["Invoices"].kwargs[-1] == {"value_input_option": "RAW"}
