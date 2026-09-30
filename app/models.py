from pydantic import BaseModel, Field

TOTAL_TOLERANCE = 0.02


class LineItem(BaseModel):
    description: str | None = Field(None, description="What was sold or the service provided")
    quantity: float | None = Field(None, description="Number of units")
    unit_price: float | None = Field(None, description="Price per unit, as a plain number")
    amount: float | None = Field(None, description="Line total, as a plain number")


class Invoice(BaseModel):
    invoice_number: str | None = Field(None, description="The invoice number or ID exactly as printed")
    invoice_date: str | None = Field(None, description="Issue date in ISO format YYYY-MM-DD")
    due_date: str | None = Field(None, description="Payment due date in ISO format YYYY-MM-DD")
    supplier_name: str | None = Field(None, description="Company that issued the invoice (the seller)")
    supplier_tax_id: str | None = Field(None, description="Seller's VAT / tax / registration number")
    customer_name: str | None = Field(None, description="Company or person being billed (the buyer)")
    currency: str | None = Field(None, description="ISO 4217 currency code such as USD or EUR")
    subtotal: float | None = Field(None, description="Total before tax, as a plain number")
    tax: float | None = Field(None, description="Total tax amount, as a plain number")
    total: float | None = Field(None, description="Grand total to pay, as a plain number")
    line_items: list[LineItem] = Field(default_factory=list, description="Every line on the invoice")

    def warnings(self) -> list[str]:
        """Sanity checks so a human can spot a bad extraction in the sheet."""
        found = []
        if not self.invoice_number:
            found.append("missing invoice number")
        if self.total is None:
            found.append("missing total")
        if self.subtotal is not None and self.total is not None:
            expected = self.subtotal + (self.tax or 0)
            if abs(expected - self.total) > TOTAL_TOLERANCE:
                found.append(f"subtotal + tax = {expected:.2f} but total = {self.total:.2f}")
        return found
