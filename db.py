import os
import psycopg2
from psycopg2.extras import RealDictCursor


def get_connection():
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise RuntimeError("Falta DATABASE_URL en variables de entorno")
    return psycopg2.connect(database_url, sslmode="require")


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS messages (
        id SERIAL PRIMARY KEY,
        phone TEXT NOT NULL,
        contact_name TEXT,
        message TEXT NOT NULL,
        direction TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    );
    """)

    conn.commit()
    cur.close()
    conn.close()


def save_message(phone: str, contact_name: str, message: str, direction: str):
    conn = get_connection()
    cur = conn.cursor()

    cur.execute("""
    INSERT INTO messages (phone, contact_name, message, direction)
    VALUES (%s, %s, %s, %s);
    """, (phone, contact_name, message, direction))

    conn.commit()
    cur.close()
    conn.close()


def get_conversations():
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
    SELECT
        phone,
        MAX(COALESCE(contact_name, '')) AS contact_name,
        MAX(created_at) AS last_time,
        (
            SELECT m2.message
            FROM messages m2
            WHERE m2.phone = m.phone
            ORDER BY m2.created_at DESC, m2.id DESC
            LIMIT 1
        ) AS last_message
    FROM messages m
    GROUP BY phone
    ORDER BY last_time DESC;
    """)

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows


def get_messages_by_phone(phone: str):
    conn = get_connection()
    cur = conn.cursor(cursor_factory=RealDictCursor)

    cur.execute("""
    SELECT id, phone, contact_name, message, direction, created_at
    FROM messages
    WHERE phone = %s
    ORDER BY created_at ASC, id ASC;
    """, (phone,))

    rows = cur.fetchall()
    cur.close()
    conn.close()
    return rows