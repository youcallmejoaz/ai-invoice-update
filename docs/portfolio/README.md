# Portfolio material

What is here, and exactly what each image is. Nothing below is a screenshot of a live Meta, Gemini or Google Sheets
session: those need the owner's own accounts and are listed in [Still to capture](#still-to-capture-live-screenshots).

| File | What it is | Real or simulated |
|---|---|---|
| `01-architecture.png` | How the pieces fit together | Diagram |
| `02-sample-invoice.png` | The test invoice (`samples/sample_invoice.pdf`) and the fields extracted from it | The real file, rendered |
| `03-tests-passing.png` | `pytest -v`: all 68 offline tests | Real terminal output |
| `04-webhook-security.png` | `curl` against the running app: setup handshake, valid and forged signatures, oversized body | Real requests to the real server |
| `05-sheet-rows.png` | The rows `app/sheets.py` writes to the `Invoices` and `LineItems` tabs | Real output of the real code against an in-memory stand-in. **Not a Google Sheets screenshot.** |
| `demo-simulated.gif` | The whole pipeline, step by step, with the real data at each step | The real app code, with Meta's servers, Gemini and Google Sheets replaced by stand-ins. **Not a live run**, and labelled as such on every frame. |

The stand-ins in the GIF: Meta's Graph API is an in-process fake that serves the sample PDF and accepts replies,
Gemini returns the sample invoice's known values, and Google Sheets is an in-memory fake. Everything else (signature check,
request building, media download, file-type detection, sanity check, sheet rows, reply text) is the code in `app/`.

## Still to capture (live screenshots)

Take these yourself once the setup from the main [README](../../README.md) works. Relevant screens only:

| Save as | Screen | Hide or blur before saving |
|---|---|---|
| `live-01-meta-api-setup.png` | Meta developer dashboard > WhatsApp > API Setup: the test number under *From* and your phone in the *To* list | access token, phone numbers, account IDs |
| `live-02-meta-webhook.png` | WhatsApp > Configuration: callback URL saved, `messages` field subscribed | verify token, the app secret if visible |
| `live-03-terminal.png` | Terminal with `uvicorn` running and the request log showing `POST /whatsapp/webhook ... 200` | anything from `.env` |
| `live-04-whatsapp-chat.png` | Your phone: the PDF you sent and the two replies ("Got it!" and "Saved invoice ...") | your number and the test number |
| `live-05-google-sheet.png` | The `Invoices` tab with the new row (and `LineItems` if you like) | the sheet ID in the URL bar |

Never show the access token, app secret, verify token, `.env` or `service_account.json`. If one slips into a
screenshot, regenerate it in Meta's dashboard; blurring a token you have already published does not un-leak it.

### A real demo GIF

Record your phone screen (or a laptop window with the chat and the sheet side by side) while you send the sample
invoice, then convert it:

```bash
ffmpeg -i recording.mp4 -vf "fps=12,scale=720:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse" live-demo.gif
```

Keep it under about 15 seconds, and save it as `live-demo.gif` next to the screenshots.
