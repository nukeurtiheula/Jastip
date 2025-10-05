import os
import logging
from dotenv import load_dotenv

# Muat variabel dari file .env di direktori yang sama
load_dotenv()

# Konfigurasi Logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s", level=logging.INFO
)
logging.getLogger("httpx").setLevel(logging.WARNING)
# --- INI BARIS YANG DIPERBAIKI ---
logger = logging.getLogger(__name__)

# --- KONFIGURASI DATABASE ---
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise ValueError("Variabel 'DATABASE_URL' tidak ditemukan!")

# --- KONFIGURASI BOT ---

# Token Bot
TOKEN = os.getenv("JASTIP_BOT_TOKEN")
if not TOKEN:
    raise ValueError("Token bot 'JASTIP_BOT_TOKEN' tidak ditemukan!")

# ID Admin
ADMIN_IDS_STR = os.getenv("JASTIP_ADMIN_IDS", "")
if not ADMIN_IDS_STR:
    logger.warning("Variabel JASTIP_ADMIN_IDS tidak diatur. Tidak ada admin yang dikonfigurasi.")
    ADMIN_IDS = set()
else:
    ADMIN_IDS = {int(admin_id) for admin_id in ADMIN_IDS_STR.split(',')}

# Channel & Grup
TARGET_POST_CHAT = os.getenv("JASTIP_TARGET_POST_CHAT", "@kandangpet")
ADMIN_GROUP_ID = int(os.getenv("JASTIP_ADMIN_GROUP_ID", "-1003036455519"))

# URL File QRIS dari Supabase Storage
QRIS_URL = os.getenv("QRIS_URL")
if not QRIS_URL:
    raise ValueError("Variabel 'QRIS_URL' tidak ditemukan!")