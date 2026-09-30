# Portfolio material

What is here, and exactly what each image is. Nothing below is a screenshot of a live Meta, Gemini or Google Sheets
session: those need the owner's own accounts and are listed in [Still to capture](#still-to-capture-live-screenshots).

| File | What it is | Real or simulated |
|---|---|---|
| `01-architecture.png` | How the pieces fit together | Diagram |
| `02-sample-invoice.png` | The test invoice (`samples/sample_invoice.pdf`) and the fields extracted from it | The real file, rendered |
| `03-tests-passing.png` | `pytest -v`: all 71 offline tests | Real test run, re-typeset in two columns (the header lines and the warnings summary are trimmed) |
| `04-webhook-security.png` | `curl` against the running app: setup handshake, valid and forged signatures, oversized body | Real requests to the real server. The commands shown are the exact commands that ran; secrets come from the environment. |
| `05-sheet-rows.png` | The rows `app/sheets.py` writes to the `Invoices` and `LineItems` tabs | Real output of the real code against an in-memory stand-in. **Not a Google Sheets screenshot.** |
| `demo-simulated.gif` | The whole pipeline, step by step | The real code in `app/` handling a scripted message, with three stand-ins (below). **Not a live run**, and labelled as such on every frame. |

**What is real and what is scripted in the GIF.** Real: the signature check, the request and response handling, the
Graph API request building, the media download, file-type detection, the total check, the sheet rows and the reply text.
Scripted or replaced: the incoming message (built locally in Meta's format); Meta's servers (an in-process fake that serves
the sample PDF and accepts replies); Google Sheets (an in-memory fake); and **Gemini: `extractor.extract_invoice` itself is
replaced by a function that returns the sample invoice's known values**, so the Gemini call code does not run in the GIF.
Offline, that call is only covered by tests against a fake Gemini client (they check the file, prompt, schema and model
that are sent, not what the real service returns).

**The live path has not been run yet**: not against a live Meta account, a Gemini key, or a Google Sheet.

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
