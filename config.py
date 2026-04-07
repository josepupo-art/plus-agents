import os
from dotenv import load_dotenv

load_dotenv(r"C:\plus-agents\.env")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "").strip()
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o-mini").strip()

WA_TOKEN = os.getenv("WA_TOKEN", "").strip()
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "").strip()
WA_GRAPH_VERSION = os.getenv("WA_GRAPH_VERSION", "v22.0").strip()
WA_VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "plusaligners_verify_2026").strip()

SHEET_NAME = os.getenv("SHEET_NAME", "CRM Plus Aligners").strip()
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Leads").strip()

STATE_FILE = os.getenv("STATE_FILE", r"secrets/session_state.json").strip()