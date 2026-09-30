# ai-invoice-update

Prototype: send an invoice PDF to a WhatsApp number, Gemini reads it, and the data lands in a Google Sheet.

```
Phone (WhatsApp) --PDF--> Twilio Sandbox --webhook--> FastAPI (/whatsapp/webhook)
                                                        1. reply "Got it..." straight away
                                                        2. background: download PDF -> Gemini -> Google Sheet
                                                        3. WhatsApp reply: "Saved invoice INV-... | Acme | USD 1996.5"
```

It extracts: invoice number, invoice date, due date, supplier name and tax ID, customer name, currency,
subtotal, tax, total and every line item. Anything not printed on the invoice is left blank (Gemini is told never to guess).
If `subtotal + tax` does not equal `total`, the row gets a warning and the WhatsApp reply says so.

## Setup

You need three free accounts. Keep secrets in `.env` (git-ignored); never commit them.

1. **Gemini key**: create one at <https://aistudio.google.com/apikey> and put it in `GEMINI_API_KEY`.
2. **Google Sheet**
   - In Google Cloud, create a project, enable the *Google Sheets API*, and create a *service account*.
     Download its JSON key as `service_account.json` in the repo root.
   - Create an empty Google Sheet and share it (Editor) with the service account's email address.
   - Put the ID from the sheet URL (`docs.google.com/spreadsheets/d/<ID>/edit`) in `GOOGLE_SHEET_ID`.
   - The `Invoices` and `LineItems` tabs and their headers are created automatically.
3. **Twilio WhatsApp Sandbox**
   - In the Twilio Console open *Messaging > Try it out > Send a WhatsApp message*.
   - From your phone, send the `join <your-code>` message to the sandbox number shown there (+1 415 523 8886).
   - Copy your Account SID and Auth Token into `TWILIO_ACCOUNT_SID` and `TWILIO_AUTH_TOKEN`.

Then run it:

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env            # fill in the values above
uvicorn app.main:app --port 8000
ngrok http 8000                 # in another terminal
```

Copy the ngrok `https://...` URL into `PUBLIC_BASE_URL` in `.env` (restart the app) and paste
`https://<ngrok-url>/whatsapp/webhook` into the Sandbox setting **"When a message comes in"** (method POST).
Now send `samples/sample_invoice.pdf` from your phone to the sandbox number. A row should appear in the sheet.

With `PUBLIC_BASE_URL` set, the app rejects requests that do not carry a valid Twilio signature.
Leave it empty only for local testing.

## Try it without WhatsApp

```bash
python scripts/make_sample_invoice.py        # (re)creates samples/sample_invoice.pdf
python -m app.cli samples/sample_invoice.pdf           # Gemini only, prints JSON
python -m app.cli samples/sample_invoice.pdf --sheet   # also appends to the Google Sheet
pytest -q                                               # offline tests, no keys needed
```

The sample invoice is INV-2026-0042 from Acme Web Studio Ltd to Globex Corporation, total USD 1,996.50.

## Sheet layout

`Invoices`: Received At, From, Invoice Number, Invoice Date, Due Date, Supplier, Supplier Tax ID, Customer,
Currency, Subtotal, Tax, Total, # Line Items, Warnings.
`LineItems`: Invoice Number, Description, Quantity, Unit Price, Amount.

To change what is extracted, edit the fields in `app/models.py` and the header/row lists in `app/sheets.py`.
The Gemini model is set by `GEMINI_MODEL` (default `gemini-3.6-flash`).

## Code map

- `app/main.py`: webhook, signature check, background processing, WhatsApp replies
- `app/extractor.py`: Gemini call with a Pydantic schema, so the answer is always validated JSON
- `app/sheets.py`: Google Sheets writer (values are written RAW so invoice text can never run as a formula)
- `app/whatsapp.py`: Twilio media download, signature check and outgoing messages
- `app/models.py`: the invoice fields and the total sanity check

## Prototype limits

- The Twilio Sandbox only works for phones that sent the `join` message, and the join expires after 72 hours of inactivity.
- One attachment per message; only PDF, JPG, PNG and WebP; max 15 MB.
- Background work is in-process: if the server restarts mid-job, that invoice is lost (a real version would use a queue).
- No duplicate detection: sending the same invoice twice adds two rows.
- A real deployment needs an approved WhatsApp Business sender instead of the sandbox.
