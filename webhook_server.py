import os
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = "{}"
import requests
from flask import Flask, request, jsonify
from dotenv import load_dotenv




load_dotenv(r"C:\plus-agents\.env")

from sales_agent import run_sales_pipeline

app = Flask(__name__)

VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "plusaligners_verify_2026")
GRAPH_VERSION = os.getenv("WA_GRAPH_VERSION", "v22.0")

WA_TOKEN = os.getenv("WA_TOKEN", "").strip()
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "").strip()

print("=== ENV CHECK (startup) ===")
print("WA_PHONE_NUMBER_ID:", WA_PHONE_NUMBER_ID)
print("WA_TOKEN startswith:", (WA_TOKEN or "")[:12], "len:", len(WA_TOKEN or ""))
print("GRAPH_VERSION:", GRAPH_VERSION)
print("===========================")

SEEN_MESSAGE_IDS = set()


def safe_str(x):
    return "" if x is None else str(x)


def wa_send_text(to_wa_id: str, text: str) -> bool:
    if not WA_TOKEN or not WA_PHONE_NUMBER_ID:
        print("❌ Faltan WA_TOKEN o WA_PHONE_NUMBER_ID")
        return False

    if not to_wa_id or not text:
        print("❌ Falta destinatario o texto")
        return False

    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{WA_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to_wa_id,
        "type": "text",
        "text": {"body": text},
    }

    try:
        r = requests.post(url, headers=headers, json=payload, timeout=20)
        print("WA SEND STATUS:", r.status_code)
        if r.text:
            print("WA SEND BODY:", r.text)
        return r.status_code < 400
    except Exception as e:
        print("❌ Excepción enviando WhatsApp:", repr(e))
        return False


@app.get("/webhook")
def verify():
    mode = request.args.get("hub.mode")
    token = request.args.get("hub.verify_token")
    challenge = request.args.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN and challenge:
        return challenge, 200
    return "Forbidden", 403


@app.post("/webhook")
def webhook_post():
    data = request.get_json(silent=True) or {}
    print("📩 Mensaje recibido:", data)

    try:
        for entry in data.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {}) or {}
                messages = value.get("messages", []) or []
                contacts = value.get("contacts", []) or []

                contact_name = ""
                if contacts:
                    contact_name = safe_str(
                        (contacts[0].get("profile", {}) or {}).get("name", "")
                    )

                if not messages:
                    continue

                for msg in messages:
                    try:
                        msg_id = safe_str(msg.get("id"))
                        from_wa = safe_str(msg.get("from"))
                        msg_type = safe_str(msg.get("type"))

                        if not msg_id or not from_wa:
                            continue

                        if msg_id in SEEN_MESSAGE_IDS:
                            print(f"⚠️ Duplicado ignorado: {msg_id}")
                            continue
                        SEEN_MESSAGE_IDS.add(msg_id)

                        if msg_type != "text":
                            wa_send_text(from_wa, "Por ahora solo puedo procesar mensajes de texto 🙂")
                            continue

                        inbound_text = safe_str(
                            (msg.get("text", {}) or {}).get("body", "")
                        ).strip()

                        if not inbound_text:
                            continue

                        print(f"➡️ INBOUND from {from_wa} ({contact_name}): {inbound_text}")

                        # ❌ DESACTIVADO Sheets
                        # log_message(from_wa, contact_name, inbound_text, "inbound")

                        reply_text = run_sales_pipeline(inbound_text, from_wa)

                        # ❌ DESACTIVADO Sheets
                        # log_message(from_wa, contact_name, reply_text, "outbound")

                        if not reply_text or not reply_text.strip():
                            reply_text = "¿En qué puedo ayudarte, doc?"

                        print(f"⬅️ OUTBOUND to {from_wa}: {reply_text}")
                        wa_send_text(from_wa, reply_text)

                    except Exception as msg_error:
                        print("❌ ERROR procesando mensaje individual:", repr(msg_error))

    except Exception as e:
        print("❌ ERROR webhook:", repr(e))

    return jsonify({"ok": True}), 200


if __name__ == "main":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)