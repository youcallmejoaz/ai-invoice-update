import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    twilio_account_sid: str
    twilio_auth_token: str
    twilio_whatsapp_from: str
    google_service_account_file: str
    google_sheet_id: str
    public_base_url: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        twilio_account_sid=os.getenv("TWILIO_ACCOUNT_SID", ""),
        twilio_auth_token=os.getenv("TWILIO_AUTH_TOKEN", ""),
        twilio_whatsapp_from=os.getenv("TWILIO_WHATSAPP_FROM", "whatsapp:+14155238886"),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
        public_base_url=os.getenv("PUBLIC_BASE_URL", "").rstrip("/"),
    )
