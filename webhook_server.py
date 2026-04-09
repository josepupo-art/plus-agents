import os

# Parche para evitar crash si alguna parte vieja todavía busca esta variable
os.environ["GOOGLE_SERVICE_ACCOUNT_JSON"] = "{}"

import requests
from flask import Flask, request, jsonify, render_template_string, abort
from dotenv import load_dotenv

from db import init_db, save_message, get_conversations, get_messages_by_phone
from sales_agent import run_sales_pipeline
from functools import wraps
from flask import request, Response

PANEL_USER = os.getenv("PANEL_USER", "admin")
PANEL_PASSWORD = os.getenv("PANEL_PASSWORD", "1234")

def check_auth(username, password):
    return username == PANEL_USER and password == PANEL_PASSWORD

def authenticate():
    return Response(
        'Acceso restringido',
        401,
        {'WWW-Authenticate': 'Basic realm="Login requerido"'}
    )

def requires_auth(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated
load_dotenv(r"C:\plus-agents\.env")

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

try:
    init_db()
    print("✅ Base de datos inicializada")
except Exception as e:
    print("❌ Error inicializando DB:", repr(e))


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

                        try:
                            save_message(from_wa, contact_name, inbound_text, "inbound")
                        except Exception as db_in_error:
                            print("❌ Error guardando inbound en DB:", repr(db_in_error))

                        reply = run_sales_pipeline(inbound_text, from_wa)

                        if isinstance(reply, tuple):
                            reply_text = safe_str(reply[0])
                        else:
                            reply_text = safe_str(reply)

                        if not reply_text.strip():
                            reply_text = "¿En qué puedo ayudarte, doc?"

                        print(f"⬅️ OUTBOUND to {from_wa}: {reply_text}")

                        try:
                            save_message(from_wa, contact_name, reply_text, "outbound")
                        except Exception as db_out_error:
                            print("❌ Error guardando outbound en DB:", repr(db_out_error))

                        wa_send_text(from_wa, reply_text)

                    except Exception as msg_error:
                        print("❌ ERROR procesando mensaje individual:", repr(msg_error))

    except Exception as e:
        print("❌ ERROR webhook:", repr(e))

    return jsonify({"ok": True}), 200


@app.get("/panel")
@requires_auth
def panel():
    try:
        conversations = get_conversations()
    except Exception as e:
        return f"Error cargando conversaciones: {repr(e)}", 500

    html = """
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>Panel WhatsApp</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; background: #f5f6f8; }
            .wrap { max-width: 1100px; margin: 0 auto; padding: 24px; }
            h1 { margin-bottom: 20px; }
            .card {
                background: white; border-radius: 12px; padding: 16px 18px; margin-bottom: 12px;
                box-shadow: 0 1px 6px rgba(0,0,0,0.08);
            }
            .top { display: flex; justify-content: space-between; gap: 16px; }
            .name { font-weight: bold; font-size: 16px; }
            .phone { color: #666; font-size: 13px; margin-top: 4px; }
            .msg { margin-top: 10px; color: #222; }
            a { text-decoration: none; color: inherit; }
            .time { color: #666; white-space: nowrap; font-size: 13px; }
        </style>
    </head>
    <body>
        <div class="wrap">
            <h1>Conversaciones WhatsApp</h1>
            {% if conversations %}
                {% for c in conversations %}
                    <a href="/panel/chat/{{ c.phone }}">
                        <div class="card">
                            <div class="top">
                                <div>
                                    <div class="name">{{ c.contact_name or "Sin nombre" }}</div>
                                    <div class="phone">{{ c.phone }}</div>
                                </div>
                                <div class="time">{{ c.last_time }}</div>
                            </div>
                            <div class="msg">{{ c.last_message }}</div>
                        </div>
                    </a>
                {% endfor %}
            {% else %}
                <div class="card">Todavía no hay conversaciones guardadas.</div>
            {% endif %}
        </div>
    </body>
    </html>
    """
    return render_template_string(html, conversations=conversations)


@app.get("/panel/chat/<phone>")
@requires_auth
def panel_chat(phone):
    try:
        messages = get_messages_by_phone(phone)
    except Exception as e:
        return f"Error cargando chat: {repr(e)}", 500

    if not messages:
        abort(404)

    contact_name = messages[0].get("contact_name") or "Sin nombre"

    html = """
    <!doctype html>
    <html lang="es">
    <head>
        <meta charset="utf-8">
        <title>Chat {{ phone }}</title>
        <style>
            body { font-family: Arial, sans-serif; margin: 0; background: #efeae2; }
            .wrap { max-width: 900px; margin: 0 auto; padding: 24px; }
            .header {
                background: white; border-radius: 12px; padding: 16px 20px; margin-bottom: 18px;
                box-shadow: 0 1px 6px rgba(0,0,0,0.08);
            }
            .title { font-size: 20px; font-weight: bold; }
            .sub { color: #666; margin-top: 4px; }
            .chat { display: flex; flex-direction: column; gap: 12px; }
            .bubble {
                max-width: 75%; padding: 12px 14px; border-radius: 12px;
                box-shadow: 0 1px 4px rgba(0,0,0,0.08); white-space: pre-wrap;
            }
            .inbound { align-self: flex-start; background: white; }
            .outbound { align-self: flex-end; background: #d9fdd3; }
            .meta { font-size: 12px; color: #666; margin-top: 6px; }
            .back { display: inline-block; margin-bottom: 16px; color: #0b57d0; text-decoration: none; }
        </style>
    </head>
    <body>
        <div class="wrap">
            <a class="back" href="/panel">← Volver al panel</a>
            <div class="header">
                <div class="title">{{ contact_name }}</div>
                <div class="sub">{{ phone }}</div>
            </div>

            <div class="chat">
                {% for m in messages %}
                    <div class="bubble {{ m.direction }}">
                        {{ m.message }}
                        <div class="meta">{{ m.direction }} · {{ m.created_at }}</div>
                    </div>
                {% endfor %}
            </div>
        </div>
    </body>
    </html>
    """
    return render_template_string(
        html,
        phone=phone,
        contact_name=contact_name,
        messages=messages
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 10000))
    app.run(host="0.0.0.0", port=port)