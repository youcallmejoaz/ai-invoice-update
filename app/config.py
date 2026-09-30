import os
from dataclasses import dataclass
from functools import lru_cache

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    gemini_api_key: str
    gemini_model: str
    whatsapp_access_token: str
    whatsapp_verify_token: str
    meta_app_secret: str
    graph_api_version: str
    google_service_account_file: str
    google_sheet_id: str


@lru_cache
def get_settings() -> Settings:
    return Settings(
        gemini_api_key=os.getenv("GEMINI_API_KEY", ""),
        gemini_model=os.getenv("GEMINI_MODEL", "gemini-3.6-flash"),
        whatsapp_access_token=os.getenv("WHATSAPP_ACCESS_TOKEN", ""),
        whatsapp_verify_token=os.getenv("WHATSAPP_VERIFY_TOKEN", ""),
        meta_app_secret=os.getenv("META_APP_SECRET", ""),
        graph_api_version=os.getenv("GRAPH_API_VERSION", "v26.0"),
        google_service_account_file=os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE", "service_account.json"),
        google_sheet_id=os.getenv("GOOGLE_SHEET_ID", ""),
    )
