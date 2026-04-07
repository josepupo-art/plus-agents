import os
import pickle
import gspread

from datetime import datetime
from google.auth.transport.requests import Request
from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials

from config import SHEET_NAME, WORKSHEET_NAME

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive"
]

TOKEN_FILE = r"C:\plus-agents\secrets\token.pickle"
CREDS_FILE = r"C:\plus-agents\secrets\oauth_client.json"

EXPECTED_HEADERS = [
    "nombre",
    "telefono",
    "especialidad",
    "origen",
    "estado",
]


def get_credentials():
    creds = None

    if os.path.exists(TOKEN_FILE):
        with open(TOKEN_FILE, "rb") as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(CREDS_FILE, SCOPES)
            creds = flow.run_local_server(port=0)

        with open(TOKEN_FILE, "wb") as token:
            pickle.dump(creds, token)

    return creds


def get_client():
    creds = get_credentials()
    return gspread.authorize(creds)


def get_spreadsheet():
    gc = get_client()
    return gc.open(SHEET_NAME)


def get_worksheet():
    sh = get_spreadsheet()
    ws = sh.worksheet(WORKSHEET_NAME)
    ensure_headers(ws)
    return ws


def get_or_create_worksheet(title, headers=None, rows=1000, cols=20):
    sh = get_spreadsheet()

    try:
        ws = sh.worksheet(title)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(title=title, rows=rows, cols=cols)

    if headers:
        current = ws.row_values(1)
        if not current:
            ws.append_row(headers)

    return ws


def ensure_headers(ws):
    current = ws.row_values(1)
    if not current:
        ws.append_row(EXPECTED_HEADERS)
        return

    normalized = [str(x).strip().lower() for x in current]
    if normalized[:len(EXPECTED_HEADERS)] != EXPECTED_HEADERS:
        ws.update("A1:E1", [EXPECTED_HEADERS])


def add_lead(nombre, telefono, especialidad="odontologo", origen="manual", estado="pendiente"):
    ws = get_worksheet()
    ws.append_row([
        str(nombre or "").strip(),
        str(telefono or "").strip(),
        str(especialidad or "").strip(),
        str(origen or "").strip(),
        str(estado or "").strip().lower(),
    ])


def get_all_leads():
    ws = get_worksheet()
    return ws.get_all_records()


def get_leads_for_campaign(limit=30):
    rows = get_all_leads()
    leads = []

    for r in rows:
        estado = str(r.get("estado", "")).strip().lower()
        telefono = str(r.get("telefono", "")).strip()

        if estado == "apto" and telefono:
            leads.append(r)

        if len(leads) >= limit:
            break

    return leads


def mark_lead_as_sent(phone: str):
    ws = get_worksheet()
    records = ws.get_all_records()

    for idx, row in enumerate(records, start=2):
        row_phone = str(row.get("telefono", "")).strip()
        if row_phone == str(phone).strip():
            ws.update_cell(idx, 5, "enviado")
            return True
    return False


def log_message(phone, name, message, direction):
    headers = ["fecha", "telefono", "nombre", "direccion", "mensaje", "origen"]
    ws = get_or_create_worksheet("Conversaciones", headers=headers, rows=2000, cols=10)

    ws.append_row([
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        str(phone or "").strip(),
        str(name or "").strip(),
        str(direction or "").strip(),
        str(message or "").strip(),
        "whatsapp"
    ])