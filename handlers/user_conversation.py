# GANTI SELURUH FILE handlers/user_conversation.py DENGAN INI

import uuid
import asyncio
from datetime import datetime, timezone
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup, InputMediaPhoto
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import constants as K
import config
import utils
from handlers.user_callbacks import build_riwayat_message

# --- Kamus Detail Paket ---
package_details = {
    'dasar': {
        'name': 'Dasar', 'price': '2.000', 'posts': 3,
        'description': "✅ *3x Kuota Posting*\n✅ *+1 Poin Reward* setiap pembelian\n\nSangat cocok untuk memulai atau mencoba layanan kami."
    },
    'hemat': {
        'name': 'Hemat', 'price': '5.000', 'posts': 7,
        'description': "✅ *7x Kuota Posting*\n\nPilihan paling populer untuk jualan reguler dengan harga terjangkau."
    },
    'sultan': {
        'name': 'Sultan', 'price': '10.000', 'posts': 15,
        'description': "✅ *15x Kuota Posting*\n\nPilihan terbaik untuk penjual paling aktif dengan harga per postingan termurah."
    }
}

async def job_transition_to_main_menu(context: ContextTypes.DEFAULT_TYPE):
    """Fungsi pembungkus yang dipanggil oleh JobQueue."""
    job_data = context.job.data
    await utils.transition_to_main_menu(
        context=context,
        chat_id=job_data['user_id'],
        message_id=job_data['message_id'],
        username=job_data['username']
    )

# ==============================================================================
# --- MENU UTAMA & PEMBATALAN ---
# ==============================================================================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    chat_id = update.effective_chat.id
    if db.get_setting('maintenance_mode', 'off') == 'on' and not utils.is_admin(user.id):
        try:
            await context.bot.send_message(user.id, "🔧 Maaf, bot sedang dalam perbaikan. Silakan coba lagi nanti.")
        except Exception:
            pass
        return ConversationHandler.END

    try:
        if db.is_user_banned(user.id):
            await context.bot.send_message(user.id, "🚫 Akun Anda telah diblokir.")
            return ConversationHandler.END
            
        user_reward_data = db.get_user_data(user.id)
        if user_reward_data and user_reward_data['last_menu_id']:
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=user_reward_data['last_menu_id'])
            except Exception:
                pass
                
        text, keyboard = utils.build_main_menu_message(user.id, user.username or "User")
        menu_msg = await context.bot.send_message(chat_id, text, reply_markup=keyboard, parse_mode="Markdown")
        
        db.db_execute("INSERT INTO user_rewards (u_id) VALUES (%s) ON CONFLICT (u_id) DO NOTHING;", (user.id,))
        db.db_execute("UPDATE user_rewards SET last_menu_id = %s WHERE u_id = %s", (menu_msg.message_id, user.id))

    except Exception as e:
        # Jika ada error database, cetak ke Vercel Logs dan beri tahu user
        config.logger.error(f"DATABASE ERROR in start handler: {e}", exc_info=True)
        await context.bot.send_message(chat_id, "⚠️ Maaf, terjadi kesalahan saat mengambil data Anda. Coba lagi nanti.")
        return ConversationHandler.END
    return ConversationHandler.END

async def cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    for key in ['interactive_message_id', 'preview_msg_id', 'qris_msg_id']:
        if msg_id := context.user_data.pop(key, None):
            try: await context.bot.delete_message(user_id, msg_id)
            except: pass

    try:
        if update.message: await update.message.delete()
    except: pass
    context.user_data.clear()
    
    cancel_msg = await context.bot.send_message(user_id, "ℹ️ Aksi dibatalkan.")
    context.job_queue.run_once(utils.delete_message_after_delay, 2, chat_id=user_id, data={'message_id': cancel_msg.message_id})
    await start(update, context)
    return ConversationHandler.END

# ==============================================================================
# --- ALUR PEMBELIAN PAKET ---
# ==============================================================================

async def view_packages_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    text = (
        "🛍️ *Pilih Paket Jastip*\n\n"
        "Tingkatkan jangkauan jualanmu dengan paket unggulan kami!\n\n"
        "▫️ *Paket Dasar* - *Rp 2.000*\n"
        "└─ `3x Kuota Posting` | `+1 Poin Reward`\n\n"
        "▫️ *Paket Hemat* - *Rp 5.000*\n"
        "└─ `7x Kuota Posting`\n\n"
        "👑 *Paket Sultan* - *Rp 10.000*\n"
        "└─ `15x Kuota Posting`\n\n"
        "Pilih paket yang ingin Anda beli:")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Beli Dasar", callback_data="buy_package:dasar"), InlineKeyboardButton("Beli Hemat", callback_data="buy_package:hemat")],
        [InlineKeyboardButton("Beli Sultan", callback_data="buy_package:sultan")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="back_to_main_menu")]])
    try:
        await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    except Exception:
        try: await query.message.delete()
        except: pass
        await context.bot.send_message(query.from_user.id, text, reply_markup=keyboard, parse_mode="Markdown")
    return ConversationHandler.END

async def buy_package_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    package_name = query.data.split(':')[1]
    details = package_details.get(package_name)
    if not details:
        return await query.edit_message_text("❌ Paket tidak ditemukan.")
    text = (
        f"🛍️ *Detail Paket {details['name']}*\n\n"
        f"{details['description']}\n\n"
        f"Harga: *Rp {details['price']}*"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton(f"✅ Beli Paket Ini", callback_data=f"proceed_payment:{package_name}")],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar Paket", callback_data="view_packages")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def proceed_to_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    package_name = query.data.split(':')[1]
    context.user_data['package_to_buy'] = package_name
    details = package_details.get(package_name)
    text = (f"Anda akan membeli *Paket {details['name']}* seharga *Rp {details['price']}*.\n\n"
            "Silakan lakukan pembayaran ke QRIS di atas, lalu kirim bukti transfer Anda di chat ini.")
    media = InputMediaPhoto(media=config.QRIS_URL, caption=text, parse_mode="Markdown")
    message = await query.edit_message_media(media=media)
    context.user_data['message_id'] = message.message_id
    return K.STATE_WAITING_PACKAGE_PAYMENT

# File: handlers/user_conversation.py

async def package_payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    config.logger.info(f"[Payment Paket] Menerima bukti pembayaran dari user: {user.id}")

    try:
        package_name = context.user_data.get('package_to_buy')
        if not package_name:
            await update.message.reply_text("Sesi pembelian tidak ditemukan. Silakan ulangi.")
            return ConversationHandler.END

        payment_file_id = update.message.photo[-1].file_id if update.message.photo else None
        if not payment_file_id:
            await update.message.reply_text("⚠️ Harap kirim bukti pembayaran berupa FOTO.")
            return K.STATE_WAITING_PACKAGE_PAYMENT

        proof_msg_id = update.message.message_id
        qris_msg_id = context.user_data.pop('message_id', None)

        config.logger.info(f"[Payment Paket] Mencoba update DB untuk user: {user.id}")
        # --- PERHATIKAN QUERY INI, PASTIKAN MENGGUNAKAN %s ---
        db.db_execute("""
            UPDATE user_rewards 
            SET pending_qris_msg_id = %s, pending_proof_msg_id = %s 
            WHERE u_id = %s
        """, (qris_msg_id, proof_msg_id, user.id))
        config.logger.info(f"[Payment Paket] BERHASIL update DB untuk user: {user.id}")
        
        admin_caption = (f"🛍️ *Pembelian Paket {package_name.title()}*\n\n"
                         f"Dari: @{user.username or user.full_name} (`{user.id}`)")
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(f"✅ Konfirmasi Paket", callback_data=f"confirm_package:{package_name}:{user.id}")]])
        await context.bot.send_photo(
            config.ADMIN_GROUP_ID, photo=payment_file_id, caption=admin_caption,
            parse_mode="Markdown", reply_markup=keyboard)

        notif_text = "✅ Bukti pembayaran diterima dan sedang diverifikasi oleh admin. Pesan ini akan otomatis terhapus setelah dikonfirmasi."
        await context.bot.send_message(user.id, notif_text, parse_mode="Markdown")
        
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        config.logger.error(f"[Payment Paket] GAGAL TOTAL untuk user {user.id}: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Maaf, terjadi kesalahan teknis saat memproses bukti pembayaran Anda. Silakan hubungi admin.")
        return ConversationHandler.END

# ==============================================================================
# --- ALUR SUBMIT BARU ---
# ==============================================================================

async def mulai_submit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    user_id = query.from_user.id
    if db.get_setting('maintenance_mode', 'off') == 'on' and not utils.is_admin(user_id):
        await query.answer("🔧 Maaf, bot sedang dalam perbaikan. Fitur submit dinonaktifkan sementara.", show_alert=True)
        return ConversationHandler.END
    if db.is_user_banned(user_id):
        await query.answer("🚫 Akun Anda telah diblokir.", show_alert=True)
        return ConversationHandler.END
    await query.answer()
    text = ("🤖 *LANGKAH 1/3: KIRIM FOTO PET*\n\n"
            "Silakan upload 1 foto. Grid dahulu jika lebih dari 1.\n"
            "*(Sertakan deskripsi/caption langsung pada foto jika memungkinkan)*")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Batalkan 🚫", callback_data="cancel_submission")]])
    if query.message.photo:
        try: await query.message.delete()
        except Exception: pass
        msg = await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
        context.user_data['interactive_message_id'] = msg.message_id
    else:
        try:
            await query.edit_message_text(text, parse_mode="Markdown", reply_markup=keyboard)
            context.user_data['interactive_message_id'] = query.message.message_id
        except Exception as e:
            config.logger.warning(f"Gagal edit dari teks, mengirim ulang: {e}")
            try: await query.message.delete()
            except: pass
            msg = await context.bot.send_message(user_id, text, parse_mode="Markdown", reply_markup=keyboard)
            context.user_data['interactive_message_id'] = msg.message_id
    db.db_execute("UPDATE user_rewards SET last_menu_id = NULL WHERE u_id = %s", (user_id,))
    return K.STATE_PHOTO

async def photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    interactive_msg_id = context.user_data.get('interactive_message_id')
    if not interactive_msg_id: return ConversationHandler.END
    try: await update.message.delete()
    except: pass
    context.user_data["photo_file_id"] = update.message.photo[-1].file_id
    if update.message.caption:
        context.user_data["pet_name"] = update.message.caption_html
        return await ke_langkah_username(update, context)
    caption = ("✅ *Foto diterima!*\n"
               "🤖 *LANGKAH 2/3: MASUKKAN LIST PET*\n\n"
               "Sekarang, ketik *deskripsi atau list pet* yang ingin Anda jual.")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Ganti Foto", callback_data="edit_photo_step")],
        [InlineKeyboardButton("Batalkan 🚫", callback_data="cancel_submission")]
    ])
    media = InputMediaPhoto(media=context.user_data["photo_file_id"], caption=caption, parse_mode="Markdown")
    await context.bot.edit_message_media(
        chat_id=update.effective_chat.id, message_id=interactive_msg_id,
        media=media, reply_markup=keyboard)
    return K.STATE_PET_FORMAT

async def pet_format_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["pet_name"] = update.message.text_html
    try: await update.message.delete()
    except: pass
    return await ke_langkah_username(update, context)

async def ke_langkah_username(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    interactive_msg_id = context.user_data.get('interactive_message_id')
    if not interactive_msg_id: return ConversationHandler.END
    if not context.user_data.get('pet_name'):
        config.logger.error("ke_langkah_username dipanggil tanpa pet_name.")
        return ConversationHandler.END
    preview_text = (
        f"{context.user_data['pet_name']}\n\n"
        "-------------------------------------\n"
        "✅ <b>Deskripsi diterima!</b>\n"
        "🤖 <b>LANGKAH 3/3: MASUKKAN USERNAME</b>\n\n"
        "Terakhir, ketik username Telegram Anda.\n<b>Contoh:</b> @kandangpet")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Edit Deskripsi", callback_data="edit_desc_step")],
        [InlineKeyboardButton("Batalkan 🚫", callback_data="cancel_submission")]
    ])
    media = InputMediaPhoto(media=context.user_data['photo_file_id'], caption=preview_text, parse_mode="HTML")
    await context.bot.edit_message_media(
        chat_id=update.effective_chat.id, message_id=interactive_msg_id, media=media, reply_markup=keyboard)
    return K.STATE_USER_TELE

async def user_tele_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user = update.effective_user
    interactive_msg_id = context.user_data.get('interactive_message_id')
    if not interactive_msg_id: return ConversationHandler.END
    context.user_data["user_tele"] = update.message.text.strip()
    try: await update.message.delete()
    except: pass
    await tampilkan_preview_final(update, context)
    return K.STATE_FINAL_CONFIRM

async def tampilkan_preview_final(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    # --- PERBAIKAN UTAMA ADA DI CARA MEMBUAT CAPTION ---
    
    # Ambil data dari context
    pet_name_html = context.user_data.get('pet_name', '')
    user_tele_plain = context.user_data.get('user_tele', '')

    # Gunakan f-string untuk memasukkan deskripsi HTML secara langsung
    caption = (
        f"✨ <b>PREVIEW FINAL</b>\n\n"
        f"Mohon periksa kembali detail pengajuan Anda di bawah ini.\n\n"
        f"<b>Deskripsi:</b>\n{pet_name_html}\n\n"
        f"<b>Username Kontak:</b>\n<code>{user_tele_plain}</code>\n\n"
        f"Apakah data di atas sudah benar?"
    )
    
    # --- SISA KODE TIDAK BERUBAH ---
    
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Lanjutkan", callback_data="confirm_final_continue")],
        [InlineKeyboardButton("✏️ Edit Data", callback_data="confirm_final_edit")],
        [InlineKeyboardButton("🚫 Batalkan", callback_data="confirm_final_cancel")]])
    
    # Hapus pesan interaktif sebelumnya
    interactive_msg_id = context.user_data.pop('interactive_message_id', None)
    if interactive_msg_id:
        try:
            await context.bot.delete_message(chat_id=user.id, message_id=interactive_msg_id)
        except:
            pass
        
    preview_msg = await context.bot.send_photo(
        chat_id=user.id,
        photo=context.user_data['photo_file_id'],
        caption=caption,
        parse_mode="HTML", # Pastikan parse_mode adalah HTML
        reply_markup=keyboard
    )
    context.user_data['preview_msg_id'] = preview_msg.message_id

async def confirm_final_continue_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    user = query.from_user
    submission_data = {
        "unique_id": str(uuid.uuid4()), "timestamp": datetime.now(timezone.utc).isoformat(),
        "u_id": user.id, "u_name": user.username or user.full_name, "status": "pending",
        "post_link": "", "is_reward": 0, "submission_msg_id": None, **context.user_data
    }
    user_data = db.get_user_data(user.id) or {}
    admin_caption_prefix = "🆕 <b>Pengajuan Jastip Baru (Berbayar)</b>"
    kuota_terpakai = False
    
    if user_data.get('available_rewards', 0) > 0:
        db.db_execute("UPDATE user_rewards SET available_rewards = available_rewards - 1 WHERE u_id = %s", (user.id,))
        submission_data["is_reward"] = 1; admin_caption_prefix = "🎁 <b>PENGAJUAN REWARD (GRATIS)</b>"; kuota_terpakai = True
    elif user_data.get('paket_sultan_posts', 0) > 0:
        db.db_execute("UPDATE user_rewards SET paket_sultan_posts = paket_sultan_posts - 1 WHERE u_id = %s", (user.id,))
        admin_caption_prefix = "👑 <b>PENGAJUAN PAKET SULTAN</b>"; kuota_terpakai = True
    elif user_data.get('paket_hemat_posts', 0) > 0:
        db.db_execute("UPDATE user_rewards SET paket_hemat_posts = paket_hemat_posts - 1 WHERE u_id = %s", (user.id,))
        admin_caption_prefix = "🎟️ <b>PENGAJUAN PAKET HEMAT</b>"; kuota_terpakai = True
    elif user_data.get('paket_dasar_posts', 0) > 0:
        db.db_execute("UPDATE user_rewards SET paket_dasar_posts = paket_dasar_posts - 1 WHERE u_id = %s", (user.id,))
        admin_caption_prefix = "🎟️ <b>PENGAJUAN PAKET DASAR</b>"; kuota_terpakai = True
        
    if not kuota_terpakai:
        if preview_msg_id := context.user_data.pop('preview_msg_id', None):
            try: await context.bot.delete_message(chat_id=user.id, message_id=preview_msg_id)
            except: pass
        admin_caption = (f"{admin_caption_prefix}\n\n{submission_data['pet_name']}\n\n"
                         f"User: {submission_data['user_tele']}\nOleh: @{user.username or user.full_name}\nID: <code>{submission_data['unique_id']}</code>")
        msg_admin = await context.bot.send_photo(config.ADMIN_GROUP_ID, submission_data['photo_file_id'], caption=admin_caption, parse_mode="HTML")
        submission_data["submission_msg_id"] = msg_admin.message_id
        qris_caption = "✅ Data Anda sudah benar. Silakan lakukan pembayaran *Rp 1.000* untuk melanjutkan, lalu kirim bukti transfer di chat ini."
        qris_msg = await context.bot.send_photo(chat_id=user.id, photo=config.QRIS_URL, caption=qris_caption, parse_mode="Markdown")
        context.user_data['qris_msg_id'] = qris_msg.message_id
        db.add_submission(submission_data)
        return K.STATE_WAITING_PAYMENT

    if preview_msg_id := context.user_data.pop('preview_msg_id', None):
        try: await context.bot.delete_message(chat_id=user.id, message_id=preview_msg_id)
        except: pass
    admin_caption = (f"{admin_caption_prefix}\n\n{submission_data['pet_name']}\n\n"
                     f"User: {submission_data['user_tele']}\nOleh: @{user.username or user.full_name}\nID: <code>{submission_data['unique_id']}</code>")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Langsung Post", callback_data=f"post:{submission_data['unique_id']}")]])
    msg_admin = await context.bot.send_photo(config.ADMIN_GROUP_ID, submission_data['photo_file_id'], caption=admin_caption, parse_mode="HTML", reply_markup=keyboard)
    submission_data["submission_msg_id"] = msg_admin.message_id
    confirmation_text = "✅ *Pengajuan Terkirim!*\nKuota Anda telah digunakan. Pengajuan akan segera diposting oleh admin."
    sent_confirmation_msg = await context.bot.send_message(user.id, confirmation_text, parse_mode="Markdown")
    context.job_queue.run_once(utils.delete_message_after_delay, 5, chat_id=user.id, data={'message_id': sent_confirmation_msg.message_id})
    submission_data["user_confirmation_msg_id"] = sent_confirmation_msg.message_id
    db.add_submission(submission_data)
    await start(update, context)
    context.user_data.clear()
    return ConversationHandler.END

async def confirm_final_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Ganti Foto", callback_data="edit_final_photo")],
        [InlineKeyboardButton("📝 Edit Deskripsi", callback_data="edit_final_desc")],
        [InlineKeyboardButton("👤 Edit Username", callback_data="edit_final_user")],
        [InlineKeyboardButton("⬅️ Kembali ke Preview", callback_data="edit_final_back")]
    ])
    await query.edit_message_caption(caption="✏️ *Pilih data yang ingin Anda ubah:*", reply_markup=keyboard, parse_mode="Markdown")
    return K.STATE_FINAL_CONFIRM

async def edit_final_choice_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    choice = query.data.split('_')[-1]
    if choice == 'back':
        if preview_msg_id := context.user_data.get('preview_msg_id'):
            try: await context.bot.delete_message(chat_id=query.from_user.id, message_id=preview_msg_id)
            except: pass
        await tampilkan_preview_final(update, context)
        return K.STATE_FINAL_CONFIRM
    edit_instructions = {'photo': "📸 Silakan kirim *foto baru*.", 'desc': "📝 Silakan ketik *deskripsi baru*.", 'user': "👤 Silakan ketik *username baru*."}
    await query.edit_message_caption(caption=edit_instructions[choice], parse_mode="Markdown")
    state_map = {'photo': K.STATE_EDIT_PHOTO_CONFIRM, 'desc': K.STATE_EDIT_DESC_CONFIRM, 'user': K.STATE_EDIT_USER_CONFIRM}
    return state_map[choice]

async def edit_photo_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: await update.message.delete()
    except: pass
    context.user_data['photo_file_id'] = update.message.photo[-1].file_id
    if preview_msg_id := context.user_data.get('preview_msg_id'):
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=preview_msg_id)
        except: pass
    await tampilkan_preview_final(update, context)
    return K.STATE_FINAL_CONFIRM

async def edit_desc_handler_from_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: await update.message.delete()
    except: pass
    context.user_data['pet_name'] = update.message.text_html
    if preview_msg_id := context.user_data.get('preview_msg_id'):
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=preview_msg_id)
        except: pass
    await tampilkan_preview_final(update, context)
    return K.STATE_FINAL_CONFIRM

async def edit_user_handler_from_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    try: await update.message.delete()
    except: pass
    context.user_data['user_tele'] = update.message.text.strip()
    if preview_msg_id := context.user_data.get('preview_msg_id'):
        try: await context.bot.delete_message(chat_id=update.effective_chat.id, message_id=preview_msg_id)
        except: pass
    await tampilkan_preview_final(update, context)
    return K.STATE_FINAL_CONFIRM

# Di dalam file handlers/user_conversation.py
# Ganti seluruh fungsi ini

# File: handlers/user_conversation.py

async def payment_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    user_id = update.effective_user.id
    config.logger.info(f"[Payment Satuan] Menerima bukti pembayaran dari user: {user_id}")

    try:
        submission = db.get_last_pending_submission_by_user(user_id)
        if not submission:
            config.logger.warning(f"[Payment Satuan] Sesi submission tidak ditemukan untuk user: {user_id}")
            await update.message.reply_text("Sesi tidak ditemukan. Silakan /start ulang.")
            return ConversationHandler.END
        
        config.logger.info(f"[Payment Satuan] Sesi ditemukan untuk ID: {submission['unique_id']}")

        payment_file_id = update.message.photo[-1].file_id if update.message.photo else None
        if not payment_file_id:
            await update.message.reply_text("⚠️ Gagal! Harap kirim bukti pembayaran berupa FOTO.")
            return K.STATE_WAITING_PAYMENT

        proof_msg_id = update.message.message_id
        qris_msg_id = context.user_data.pop('qris_msg_id', None)
        unique_id = submission['unique_id']
        
        final_text = "✅ *Pembayaran Terkirim!*\n\nTerima kasih. Bukti pembayaran Anda telah kami terima dan akan segera diperiksa oleh admin. Pesan ini akan otomatis terhapus setelah dikonfirmasi."
        sent_notice_msg = await context.bot.send_message(user_id, final_text, parse_mode="Markdown")
        notice_msg_id = sent_notice_msg.message_id
        
        config.logger.info(f"[Payment Satuan] Mencoba update DB untuk ID: {unique_id}")
        db.update_submission(unique_id, {
            "bot_qris_msg_id": qris_msg_id,
            "user_proof_msg_id": proof_msg_id,
            "user_notice_msg_id": notice_msg_id
        })
        config.logger.info(f"[Payment Satuan] BERHASIL update DB untuk ID: {unique_id}")
        
        admin_caption = f"💰 *Bukti Pembayaran Diterima (Satuan)*\nID: `{unique_id}`"
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("✅ Konfirmasi & Beri Poin", callback_data=f"confirm_payment:{unique_id}")]])
        await context.bot.send_photo(config.ADMIN_GROUP_ID, payment_file_id, caption=admin_caption, reply_markup=keyboard, parse_mode="Markdown")
        
        context.user_data.clear()
        return ConversationHandler.END

    except Exception as e:
        config.logger.error(f"[Payment Satuan] GAGAL TOTAL untuk user {user_id}: {e}", exc_info=True)
        await update.message.reply_text("⚠️ Maaf, terjadi kesalahan teknis saat memproses bukti pembayaran Anda. Silakan hubungi admin.")
        return ConversationHandler.END

async def cancel_submission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.answer()
    return await cancel(update, context)

async def back_to_photo_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    try: await query.message.delete()
    except Exception: pass
    text = "🤖 *LANGKAH 1/3: GANTI FOTO PET*\n\nSilakan upload satu foto baru untuk menggantikan yang sebelumnya."
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("Batalkan 🚫", callback_data="cancel_submission")]])
    msg = await context.bot.send_message(query.from_user.id, text, parse_mode="Markdown", reply_markup=keyboard)
    context.user_data['interactive_message_id'] = msg.message_id
    return K.STATE_PHOTO

async def back_to_desc_step(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    caption = "🤖 *LANGKAH 2/3: EDIT DESKRIPSI*\n\nSilakan ketik ulang *deskripsi atau list pet* yang ingin Anda jual."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⬅️ Ganti Foto", callback_data="edit_photo_step")],
        [InlineKeyboardButton("Batalkan 🚫", callback_data="cancel_submission")]
    ])
    await query.edit_message_caption(caption=caption, parse_mode="Markdown", reply_markup=keyboard)
    return K.STATE_PET_FORMAT

# --- Alur Edit (Dari Riwayat) ---
async def user_edit_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer()
    unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not (submission and submission['u_id'] == query.from_user.id and submission['status'] != 'sold'):
        return ConversationHandler.END
    context.user_data['edit_unique_id'] = unique_id
    context.user_data['edit_messages_to_delete'] = [query.message.message_id]
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("📝 Edit Deskripsi Pet", callback_data="edit_choice_desc")],
        [InlineKeyboardButton("👤 Edit Username Tele", callback_data="edit_choice_user")],
        [InlineKeyboardButton("🚫 Batal", callback_data="edit_choice_cancel")]])
    msg = await query.message.reply_text("✏️ *Apa yang ingin kamu edit?*", reply_markup=keyboard, parse_mode="Markdown")
    context.user_data['edit_messages_to_delete'].append(msg.message_id)
    return K.STATE_EDIT_CHOICE

async def edit_choice_desc_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.delete()
    msg = await context.bot.send_message(query.from_user.id, "✏️ Kirim *deskripsi baru*.\n\nKetik /cancel untuk batal.", parse_mode="Markdown")
    context.user_data['edit_messages_to_delete'].append(msg.message_id)
    return K.STATE_EDIT_DESC

async def edit_choice_user_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query
    await query.message.delete()
    msg = await context.bot.send_message(query.from_user.id, "👤 Kirim *username baru*.\nContoh: `@kandangpet`\n\nKetik /cancel.", parse_mode="Markdown")
    context.user_data['edit_messages_to_delete'].append(msg.message_id)
    return K.STATE_EDIT_USER

async def edit_desc_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_description"] = update.message.text_html
    return await finish_editing_process(update, context)

async def edit_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    context.user_data["new_username"] = update.message.text.strip()
    return await finish_editing_process(update, context)

async def edit_choice_cancel_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; await query.answer("Proses edit dibatalkan.")
    await query.message.delete()
    context.user_data.clear()
    user_items = db.get_submissions_by_user(query.from_user.id)
    caption, reply_markup, photo_id = await build_riwayat_message(user_items, 0)
    if photo_id:
        await context.bot.send_photo(query.from_user.id, photo_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    else:
        await context.bot.send_message(query.from_user.id, caption, reply_markup=reply_markup)
    return ConversationHandler.END

# GANTI SELURUH FUNGSI INI DI handlers/user_conversation.py

async def finish_editing_process(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    unique_id = context.user_data.get("edit_unique_id")
    if not unique_id: 
        # Jika sesi hilang, batalkan saja dengan aman
        context.user_data.clear()
        return ConversationHandler.END

    # Update database terlebih dahulu
    if "new_description" in context.user_data:
        db.update_submission(unique_id, {"pet_name": context.user_data["new_description"]})
    if "new_username" in context.user_data:
        db.update_submission(unique_id, {"user_tele": context.user_data["new_username"]})

    processing_msg = await update.message.reply_text("⏳ Memperbarui postingan Anda...")
    
    # Hapus pesan-pesan interaktif
    ids_to_delete = context.user_data.get('edit_messages_to_delete', [])
    ids_to_delete.append(update.message.message_id)
    for msg_id in set(ids_to_delete):
        try:
            await context.bot.delete_message(update.effective_chat.id, msg_id)
        except Exception:
            pass

    # Ambil data terbaru dari database
    submission = db.get_submission_by_id(unique_id)
    
    # Edit pesan di channel jika ada (sudah dengan penanganan error HTML)
    if submission and submission['post_link']:
        try:
            # ... (kode try-except untuk edit caption channel tidak perlu diubah, sudah benar)
            msg_id = int(submission['post_link'].split("/")[-1])
            new_caption = (f"<b>#TITIP</b>\n<b>FOR SALE !!!</b>\n\n{submission['pet_name']}\n\n"
                           f"Note:\nPet ini bukan milik @kandangpet, disarankan menggunakan rekber.\n\n"
                           f"🛒 DM to order! : {submission['user_tele']}\n"
                           f"🚀 Subs Channel: @kandangpet\n💸 Payment: e-wallet/Avrek")
            user_tele = submission['user_tele'].strip()
            username = user_tele[1:] if user_tele.startswith('@') else (user_tele.split('t.me/')[-1] if 't.me/' in user_tele else user_tele)
            post_link = submission.get('post_link')
            first_row = [InlineKeyboardButton("🛒 DM Seller", url=f"https://t.me/{username}")]
            if post_link:
                first_row.append(InlineKeyboardButton("🔗 Cek Postingan", url=post_link))
            keyboard = InlineKeyboardMarkup([
                first_row,
                [InlineKeyboardButton("📝 Mau Jastip Juga?", url=f"https://t.me/{context.bot.username}")]
            ])
            await context.bot.edit_message_caption(
                chat_id=config.TARGET_POST_CHAT, message_id=msg_id,
                caption=new_caption, reply_markup=keyboard, parse_mode="HTML"
            )
        except BadRequest as e:
            if "can't parse entities" in str(e):
                error_text = (
                    "❌ **Gagal Update Postingan!**\n\n"
                    "Format HTML di deskripsi barumu salah (contoh: `<b>` lupa ditutup `</b>`).\n\n"
                    "Silakan **Edit** lagi dari menu riwayat dengan format yang benar."
                )
                await context.bot.send_message(update.effective_chat.id, error_text, parse_mode="Markdown")
        except Exception as e:
            config.logger.error(f"Gagal edit caption channel saat finish_editing_process: {e}")

    # Tampilkan kembali menu riwayat
    await processing_msg.delete()
    
    user_items = db.get_submissions_by_user(update.effective_user.id)
    page_to_show = next((i for i, item in enumerate(user_items) if item['unique_id'] == unique_id), 0)
    caption, reply_markup, photo_id = await build_riwayat_message(user_items, page_to_show)
    if photo_id:
        await context.bot.send_photo(update.effective_chat.id, photo=photo_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    
    # Hapus semua sisa data sesi dan AKHIRI percakapan
    context.user_data.clear()
    return ConversationHandler.END

# Di dalam file handlers/user_conversation.py
# TAMBAHKAN FUNGSI BARU INI

async def cancel_riwayat_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan alur edit dari menu riwayat secara spesifik."""
    user_id = update.effective_user.id
    
    # 1. Hapus semua pesan yang sudah kita lacak (termasuk pesan prompt)
    if 'edit_messages_to_delete' in context.user_data:
        for msg_id in context.user_data.get('edit_messages_to_delete', []):
            try:
                await context.bot.delete_message(chat_id=user_id, message_id=msg_id)
            except Exception:
                pass # Abaikan jika pesan sudah terhapus

    # 2. Hapus pesan perintah /cancel dari pengguna
    try:
        await update.message.delete()
    except Exception:
        pass
        
    # 3. Beri notifikasi singkat bahwa aksi dibatalkan
    cancel_msg = await context.bot.send_message(user_id, "ℹ️ Proses edit dibatalkan.")
    context.job_queue.run_once(utils.delete_message_after_delay, 2, chat_id=user_id, data={'message_id': cancel_msg.message_id})

    # 4. Bangun ulang dan tampilkan kembali menu Riwayat Aktif
    user_items = db.get_submissions_by_user(user_id)
    # Kembali ke halaman pertama riwayat
    caption, reply_markup, photo_id = await build_riwayat_message(user_items, 0)
    if photo_id:
        await context.bot.send_photo(user_id, photo_id, caption=caption, parse_mode="HTML", reply_markup=reply_markup)
    else:
        # Jika tidak ada riwayat aktif lagi, kirim pesan teks
        await context.bot.send_message(user_id, caption, reply_markup=reply_markup, parse_mode="HTML")

    # 5. Bersihkan data sesi dan akhiri percakapan
    context.user_data.clear()
    return ConversationHandler.END