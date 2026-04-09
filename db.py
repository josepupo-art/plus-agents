import os
import psycopg2


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