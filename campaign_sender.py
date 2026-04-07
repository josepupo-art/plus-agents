import time
import logging

from sheets_client import get_leads_for_campaign, mark_lead_as_sent
from whatsapp_client import send_text

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)

BATCH_SIZE = 30
DELAY_SECONDS = 3

WELCOME_TEXT = (
    "Hola Doc soy del equipo de Plus Aligners.\n\n"
    "Estamos compartiendo info sobre alineadores termoactivos con memoria de forma. "
    "Es una tecnologia que en muchos casos reduce o directamente evitan el uso de ataches. Ya los conoce?"
)


def is_valid_phone(phone: str) -> bool:
    digits = "".join(ch for ch in str(phone) if ch.isdigit())
    return len(digits) >= 10


def run_campaign():
    leads = get_leads_for_campaign(limit=BATCH_SIZE)

    if not leads:
        logger.warning("No hay leads aptos para enviar.")
        return

    sent = 0
    skipped = 0
    failed = 0

    for i, lead in enumerate(leads, start=1):
        phone = str(lead.get("telefono", "")).strip()
        name = str(lead.get("nombre", "")).strip()

        if not is_valid_phone(phone):
            logger.warning(f"[{i}] Teléfono inválido: {name} | {phone}")
            skipped += 1
            continue

        try:
            logger.info(f"[{i}] Enviando a {name or 'Sin nombre'} | {phone}")
            result = send_text(phone, WELCOME_TEXT)
            logger.info(f"[{i}] OK | {result}")
            mark_lead_as_sent(phone)
            sent += 1
            time.sleep(DELAY_SECONDS)

        except Exception as e:
            logger.error(f"[{i}] Error enviando a {phone}: {e}")
            failed += 1

    logger.info(f"Finalizó campaña | enviados={sent} | omitidos={skipped} | fallidos={failed}")


if __name__ == "__main__":
    run_campaign()