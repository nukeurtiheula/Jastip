# GANTI SELURUH FILE utils.py DENGAN INI

from telegram import Update, InlineKeyboardMarkup, InlineKeyboardButton
from telegram.ext import ContextTypes
import config
import database as db

def escape_markdown_v1(text: str) -> str:
    """Membersihkan teks untuk mode parse Markdown V1 Telegram."""
    if not text:
        return ""
    # Karakter yang paling umum menyebabkan masalah di username
    escape_chars = ['_', '*', '`', '[']
    for char in escape_chars:
        text = text.replace(char, '\\' + char)
    return text

def is_admin(user_id: int) -> bool:
    """Mengecek apakah user adalah admin."""
    return user_id in config.ADMIN_IDS

async def delete_message_after_delay(context: ContextTypes.DEFAULT_TYPE):
    """Job untuk menghapus pesan setelah jeda waktu tertentu."""
    job = context.job
    try:
        await context.bot.delete_message(job.chat_id, job.data['message_id'])
    except Exception:
        pass

async def fake_answer_callback(*args, **kwargs):
    """Fungsi async kosong yang menerima argumen apa pun."""
    pass

def build_main_menu_message(user_id: int, username: str):
    """Membangun teks dan keyboard untuk menu utama yang dinamis (dasbor pengguna)."""
    user_data = db.get_user_data(user_id)
    
    # --- Statistik & Lencana ---
    on_sale_count = db.count_user_submissions_by_status(user_id, 'on sale')
    sold_count = db.count_user_submissions_by_status(user_id, 'sold')
    total_posts = on_sale_count + sold_count
    
    user_badge = ""
    if total_posts == 0:
        user_badge = "Penitip Baru 🐣"
    elif 1 <= total_posts <= 4:
        user_badge = "Penjaga Kandang 🐾"
    elif 5 <= total_posts <= 14:
        user_badge = "Paw-rent Handal 😼"
    elif 15 <= total_posts <= 29:
        user_badge = "Ranger Kandang Pet 🛡️"
    else:
        user_badge = "Sang Paw-ner 👑"

    stats_text = (
        f"🏅 Lencana Anda: *{user_badge}*\n\n"
        f"📊 *Statistik Jualan Anda*\n"
        f"  - 🏪 Jastip Aktif: *{on_sale_count}*\n"
        f"  - ✅ Jastip Sold: *{sold_count}*\n\n"
    )
    
    # --- Poin Reward ---
    progress = user_data['submission_count'] if user_data else 0
    progress_bar = "✅" * progress + "⬜️" * (5 - progress)
    reward_text = f"🎯 *Poin Reward*\n`{progress_bar}` ({progress}/5)"

    # --- Bagian Kuota ---
    kuota_texts = []
    if user_data:
        if user_data.get('available_rewards', 0) > 0:
            kuota_texts.append(f"  - 🎁 Tiket Reward: *{user_data['available_rewards']}x post*")
        if user_data.get('paket_dasar_posts', 0) > 0:
            kuota_texts.append(f"  - 🎟️ Kuota Dasar: *{user_data['paket_dasar_posts']}x post*")
        if user_data.get('paket_hemat_posts', 0) > 0:
            kuota_texts.append(f"  - 🎟️ Kuota Hemat: *{user_data['paket_hemat_posts']}x post*")
        if user_data and user_data.get('paket_sultan_posts', 0) > 0:
            kuota_texts.append(f"  - 👑 Kuota Sultan: *{user_data['paket_sultan_posts']}x post*")
    
    # --- Gabungkan Semua Bagian ---
    # INILAH PERBAIKANNYA: Bersihkan username sebelum digunakan
    safe_username = escape_markdown_v1(username)
    
    text_parts = [
        f"Halo, @{safe_username}! 👋\n",
        stats_text,
        "-------------------------------------",
        reward_text
    ]
    
    if kuota_texts:
        kuota_info = "\n".join(kuota_texts)
        text_parts.append(f"\n🛍️ *Sisa Kuota Anda:*\n{kuota_info}")

    text = "\n".join(text_parts)

    keyboard_layout = [
        [InlineKeyboardButton("📝 Mulai Jastip", callback_data="mulai_submit"), InlineKeyboardButton("📋 Riwayat Aktif", callback_data="lihat_riwayat:0")],
        [InlineKeyboardButton("🛍️ Beli Paket Jastip", callback_data="view_packages")]
    ]
    
    return text, InlineKeyboardMarkup(keyboard_layout)