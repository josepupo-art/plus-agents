import requests
from config import WA_TOKEN, WA_PHONE_NUMBER_ID, WA_GRAPH_VERSION


def send_text(phone: str, message: str) -> dict:
    if not WA_TOKEN:
        raise RuntimeError("Falta WA_TOKEN en .env")
    if not WA_PHONE_NUMBER_ID:
        raise RuntimeError("Falta WA_PHONE_NUMBER_ID en .env")
    if not phone:
        raise ValueError("Falta phone")
    if not message or not message.strip():
        raise ValueError("Falta message")

    url = f"https://graph.facebook.com/{WA_GRAPH_VERSION}/{WA_PHONE_NUMBER_ID}/messages"

    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }

    payload = {
        "messaging_product": "whatsapp",
        "to": str(phone).strip(),
        "type": "text",
        "text": {"body": message.strip()},
    }

    response = requests.post(url, headers=headers, json=payload, timeout=30)
    response.raise_for_status()
    return response.json()