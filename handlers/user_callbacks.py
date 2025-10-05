# GANTI SELURUH FILE handlers/user_callbacks.py DENGAN INI

import asyncio
from datetime import datetime
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes
import database as db
import config
import utils
from handlers import user_conversation as usr_conv
from handlers import user_callbacks as usr_cb

async def build_riwayat_message(user_items, page=0):
    """Membangun pesan dan keyboard untuk menu riwayat."""
    if not user_items:
        keyboard = InlineKeyboardMarkup([
            [InlineKeyboardButton("📝 Mulai jastip", callback_data="mulai_submit")],
            [InlineKeyboardButton("⬅️ Kembali ke Menu Utama", callback_data="back_to_main_menu")]
        ])
        return "📭 Kamu belum memiliki postingan aktif.", keyboard, None

    page = max(0, min(page, len(user_items) - 1))
    item = user_items[page]
    
    caption = (f"📖 <b>Riwayat Aktif</b> ({page + 1}/{len(user_items)})\n\n"
               f"{item['pet_name']}\n\n"
               f"📅 <b>Tanggal:</b> {datetime.fromisoformat(item['timestamp']).strftime('%d %b %Y, %H:%M')}")
    
    keyboard_layout = []

    if 'post_link' in item and item['post_link']:
        link_button = InlineKeyboardButton("🔗 Cek Postingan", url=item['post_link'])
    else:
        channel_username = str(config.TARGET_POST_CHAT).lstrip('@')
        link_button = InlineKeyboardButton("🔗 Cek Postingan", url=f"https://t.me/{channel_username}")
    
    keyboard_layout.append([link_button])
    
    keyboard_layout.append([
        InlineKeyboardButton("✏️ Edit", callback_data=f"edit:{item['unique_id']}"),
        InlineKeyboardButton("✅ Sold", callback_data=f"sold:{item['unique_id']}")
    ])
    
    nav_buttons = []
    if page > 0: nav_buttons.append(InlineKeyboardButton("<<", callback_data=f"lihat_riwayat:{page-1}"))
    if page < len(user_items) - 1: nav_buttons.append(InlineKeyboardButton(">>", callback_data=f"lihat_riwayat:{page+1}"))
    if nav_buttons: keyboard_layout.append(nav_buttons)
    
    keyboard_layout.append([
        InlineKeyboardButton("➕ Tambah Jastip", callback_data="mulai_submit"),
        InlineKeyboardButton("⬅️ Menu Utama", callback_data="back_to_main_menu")
    ])
    
    return caption, InlineKeyboardMarkup(keyboard_layout), item['photo_file_id']

async def lihat_riwayat_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu riwayat postingan aktif dengan transisi halus dan penanganan error."""
    query = update.callback_query
    await query.answer("Memuat...")
    user_id = query.from_user.id
    db.db_execute("UPDATE user_rewards SET last_menu_id = NULL WHERE u_id = %s", (user_id,))
    
    callback_data = query.data.replace('|', ':')
    page = int(callback_data.split(":")[1])
    
    user_items = db.get_submissions_by_user(user_id)
    caption, reply_markup, photo_id = await build_riwayat_message(user_items, page)

    # --- BLOK UTAMA YANG DIPERBAIKI (LEBIH TANGGUH) ---

    # Jika photo_id tidak ada dari awal, langsung kirim sebagai teks.
    if not photo_id:
        try:
            await query.edit_message_text(text=caption, reply_markup=reply_markup, parse_mode="HTML")
        except Exception as e:
            config.logger.warning(f"Gagal edit ke teks, mengirim ulang: {e}")
            try: await query.message.delete()
            except: pass
            await context.bot.send_message(user_id, caption, reply_markup=reply_markup, parse_mode="HTML")
        return

    # Jika photo_id ada, coba tampilkan sebagai media.
    try:
        media = InputMediaPhoto(media=photo_id, caption=caption, parse_mode="HTML")
        await query.edit_message_media(media=media, reply_markup=reply_markup)
    except Exception as e:
        # JIKA GAGAL (karena photo_id rusak), jangan coba kirim foto lagi.
        # Hapus pesan lama dan kirim pesan BARU dalam bentuk TEKS.
        config.logger.warning(f"Gagal edit_message_media (photo_id='{photo_id}'), mengirim ulang sebagai TEKS: {e}")
        try:
            await query.message.delete()
        except Exception:
            pass
        # Kirim fallback sebagai pesan teks, BUKAN foto.
        await context.bot.send_message(
            chat_id=user_id,
            text=caption,
            reply_markup=reply_markup,
            parse_mode="HTML"
        )
    # --- AKHIR BLOK PERBAIKAN ---

async def back_to_main_menu_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Fungsi ini sudah benar, tidak perlu diubah)
    query = update.callback_query; await query.answer()
    user = query.from_user
    text, keyboard = utils.build_main_menu_message(user.id, user.username or "User")
    try:
        if query.message.photo:
            await query.message.delete()
            menu_msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=keyboard, parse_mode="Markdown")
            message_id_to_save = menu_msg.message_id
        else:
            await query.edit_message_text(text=text, reply_markup=keyboard, parse_mode="Markdown")
            message_id_to_save = query.message.message_id
        db.db_execute("UPDATE user_rewards SET last_menu_id = %s WHERE u_id = %s", (message_id_to_save, user.id))
    except Exception as e:
        config.logger.error(f"Kegagalan total saat kembali ke menu utama: {e}")
        from handlers.user_conversation import start
        await start(update, context)

async def user_mark_sold_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Fungsi ini juga sudah diperbaiki di versi sebelumnya, tidak perlu diubah lagi)
    query = update.callback_query; await query.answer()
    callback_data = query.data.replace('|', ':'); unique_id = callback_data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not (submission and submission['u_id'] == query.from_user.id and submission['status'] == 'on sale'): return
    processing_msg = await context.bot.send_message(query.from_user.id, "⏳ Memperbarui status menjadi SOLD...")
    try: await query.message.delete()
    except Exception: pass
    db.update_submission(unique_id, {"status": "sold"})
    if submission['post_link']:
        try:
            msg_id = int(submission['post_link'].split("/")[-1])
            await context.bot.edit_message_caption(config.TARGET_POST_CHAT, msg_id, caption=f"✅ [SOLD]\n\n{submission['pet_name']}\n\nTerima kasih!", parse_mode="HTML")
        except Exception as e:
            config.logger.warning(f"Gagal mengedit caption di channel untuk {unique_id}: {e}")
    await asyncio.sleep(1)
    await context.bot.delete_message(query.from_user.id, processing_msg.message_id)
    user_items = db.get_submissions_by_user(query.from_user.id)
    caption, reply_markup, photo_id = await build_riwayat_message(user_items, 0)
    if not photo_id:
        await context.bot.send_message(query.from_user.id, caption, reply_markup=reply_markup, parse_mode="HTML")
        return
    try:
        await context.bot.send_photo(chat_id=query.from_user.id, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    except Exception as e:
        config.logger.error(f"Gagal send_photo di user_mark_sold_callback (photo_id='{photo_id}'), fallback ke teks: {e}")
        await context.bot.send_message(chat_id=query.from_user.id, text=caption, parse_mode="HTML", reply_markup=reply_markup)

async def post_pending_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Fungsi ini tidak berhubungan, tidak perlu diubah)
    pass

async def handle_unknown_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # ... (Fungsi ini sudah benar dan tangguh, tidak perlu diubah)
    query = update.callback_query; user = query.from_user; await query.answer()
    config.logger.info(f"Menangani callback usang dari user {user.id}: '{query.data}'")
    callback_data = query.data
    if callback_data.startswith("lihat_riwayat:") or callback_data.startswith("lihat_riwayat|"):
        config.logger.info("-> Rute: lihat_riwayat_callback"); return await usr_cb.lihat_riwayat_callback(update, context)
    elif callback_data == "mulai_submit":
        config.logger.info("-> Rute: mulai_submit_callback"); return await usr_conv.mulai_submit_callback(update, context)
    elif callback_data.startswith("edit:") or callback_data.startswith("edit|"):
        config.logger.info("-> Rute: user_edit_callback"); return await usr_conv.user_edit_callback(update, context)
    elif callback_data.startswith("sold:") or callback_data.startswith("sold|"):
        config.logger.info("-> Rute: user_mark_sold_callback"); return await usr_cb.user_mark_sold_callback(update, context)
    elif callback_data == "back_to_main_menu":
        config.logger.info("-> Rute: back_to_main_menu_callback"); return await usr_cb.back_to_main_menu_callback(update, context)
    elif callback_data == "view_packages":
        config.logger.info("-> Rute: view_packages_callback"); return await usr_conv.view_packages_callback(update, context)
    elif callback_data.startswith("buy_package:") or callback_data.startswith("buy_package|"):
        config.logger.info("-> Rute: buy_package_callback"); return await usr_conv.buy_package_callback(update, context)
    elif callback_data.startswith("proceed_payment:") or callback_data.startswith("proceed_payment|"):
        config.logger.info("-> Rute: proceed_to_payment_callback"); return await usr_conv.proceed_to_payment_callback(update, context)
    elif callback_data in ["cancel_submission", "confirm_final_cancel", "edit_choice_cancel"]:
        config.logger.info("-> Rute: cancel (aksi pembatalan umum)"); await query.message.delete(); return await usr_conv.cancel(update, context)
    else:
        config.logger.warning(f"-> Tidak dapat diterjemahkan: '{callback_data}'. Mengembalikan ke menu utama.")
        try: await query.message.delete()
        except: pass
        text, keyboard = utils.build_main_menu_message(user.id, user.username or "User")
        menu_msg = await context.bot.send_message(chat_id=user.id, text=text, reply_markup=keyboard, parse_mode="Markdown")
        db.db_execute("INSERT OR IGNORE INTO user_rewards (u_id) VALUES (%s)", (user.id,))
        db.db_execute("UPDATE user_rewards SET last_menu_id = %s WHERE u_id = %s", (menu_msg.message_id, user.id))