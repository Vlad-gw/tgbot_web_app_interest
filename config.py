# config.py

import os
from dotenv import load_dotenv

load_dotenv()

BOT_TOKEN = os.getenv("BOT_TOKEN")


def _parse_admin_ids(value: str) -> list[int]:
    value = (value or "").strip()
    if not value:
        return []
    parts = [p.strip() for p in value.split(",")]
    parts = [p for p in parts if p]
    return [int(p) for p in parts]


ADMIN_IDS = _parse_admin_ids(os.getenv("ADMIN_IDS"))