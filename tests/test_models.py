from app.models import Invoice


def test_consistent_invoice_has_no_warnings():
    invoice = Invoice(invoice_number="INV-1", subtotal=100, tax=10, total=110)
    assert invoice.warnings() == []


def test_total_mismatch_is_flagged():
    invoice = Invoice(invoice_number="INV-1", subtotal=100, tax=10, total=120)
    assert any("total = 120.00" in w for w in invoice.warnings())


def test_rounding_within_tolerance_is_fine():
    invoice = Invoice(invoice_number="INV-1", subtotal=33.33, tax=3.33, total=36.67)
    assert invoice.warnings() == []


def test_missing_number_and_total_are_flagged():
    assert Invoice().warnings() == ["missing invoice number", "missing total"]


def test_no_tax_line_means_subtotal_equals_total():
    assert Invoice(invoice_number="A", subtotal=50, total=50).warnings() == []
