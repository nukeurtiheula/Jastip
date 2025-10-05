# GANTI SELURUH FILE handlers/admin_callbacks.py DENGAN INI

import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import config
import utils
import constants as K

# ==============================================================================
# --- MENU UTAMA & NAVIGASI ADMIN ---
# ==============================================================================

async def admin_panel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    if not utils.is_admin(user.id): return
    text = "👑 *Panel Kendali Admin*\n\nSelamat datang, Admin! Pilih aksi di bawah ini."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("👤 Manajemen Pengguna", callback_data="admin_menu_user")],
        [InlineKeyboardButton("📂 Manajemen Pengajuan", callback_data="admin_menu_submission")],
        [InlineKeyboardButton("📊 Statistik Bot", callback_data="admin_stats")],
        [InlineKeyboardButton("📢 Broadcast Pesan", callback_data="admin_broadcast_start")],
        [InlineKeyboardButton("⚙️ Pengaturan Bot", callback_data="admin_menu_settings")]
    ])
    if update.callback_query:
        await update.callback_query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")
    else:
        if update.message:
            try: await update.message.delete()
            except: pass
        await context.bot.send_message(user.id, text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_menu_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Lihat Info & Kuota User", callback_data="admin_choose_user:info:0")],
        [InlineKeyboardButton("🚫 Ban / Unban User", callback_data="admin_menu_ban_unban")],
        [InlineKeyboardButton("🔍 Cari User", callback_data="admin_search_user_start")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back_main")]
    ])
    await query.edit_message_text("👤 *Manajemen Pengguna*\n\nPilih tindakan:", reply_markup=keyboard, parse_mode="Markdown")

async def admin_stats(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("⏳ Menghitung statistik...")
    total_users = len(db.db_execute("SELECT DISTINCT u_id FROM user_rewards", fetchall=True))
    total_on_sale = db.db_execute("SELECT COUNT(*) FROM submissions WHERE status = 'on sale'", fetchone=True)[0]
    stats_text = (
        f"📊 *Statistik Bot Jastip*\n\n"
        f"👥 Total Pengguna Terdaftar: *{total_users}*\n"
        f"🏪 Total Jastip Aktif (On Sale): *{total_on_sale}*"
    )
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back_main")]])
    await query.edit_message_text(stats_text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_menu_ban_unban(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🚫 Ban User", callback_data="admin_choose_user:ban:0")],
        [InlineKeyboardButton("✅ Unban User", callback_data="admin_choose_user:unban:0")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_user")]
    ])
    await query.edit_message_text("🚫✅ *Moderasi Pengguna*\n\nPilih tindakan:", reply_markup=keyboard, parse_mode="Markdown")

# ==============================================================================
# --- FUNGSI KONFIRMASI (PEMBAYARAN PAKET & SATUAN) ---
# ==============================================================================

async def confirm_package_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Konfirmasi diproses...")
    _, package_name, user_id_str = query.data.split(':')
    user_id = int(user_id_str)
    package_details = {'dasar': {'posts': 3, 'name': 'Dasar'}, 'hemat': {'posts': 7, 'name': 'Hemat'}, 'sultan': {'posts': 15, 'name': 'Sultan'}}
    details = package_details.get(package_name)
    if not details: return await query.edit_message_text("❌ Paket tidak valid.")
    db.db_execute("INSERT OR IGNORE INTO user_rewards (u_id) VALUES (%s)", (user_id,))
    db.db_execute(f"UPDATE user_rewards SET paket_{package_name}_posts = paket_{package_name}_posts + %s WHERE u_id = %s", (details['posts'], user_id))
    reward_diberikan = False
    if package_name == 'dasar':
        reward_diberikan = db.increment_and_check_reward(user_id)
    await query.edit_message_caption(query.message.caption_html + f"\n\n✅ *Dikonfirmasi oleh @{query.from_user.username}*", parse_mode="HTML", reply_markup=None)
    try:
        notif_text = (f"🎉 *Pembelian Berhasil!*\nPaket *{details['name']}* Anda telah aktif dengan kuota *{details['posts']}x postingan*.")
        if package_name == 'dasar': notif_text += "\n\n+1 Poin Reward ditambahkan."
        if reward_diberikan: notif_text += "\n✨ *Selamat!* Anda mendapatkan 1 Tiket Reward Gratis!"
        sent_msg = await context.bot.send_message(user_id, notif_text, parse_mode="Markdown")
        context.job_queue.run_once(utils.delete_message_after_delay, 10, chat_id=user_id, data={'message_id': sent_msg.message_id})
        user_data = db.get_user_data(user_id)
        last_menu_id = user_data.get('last_menu_id') if user_data else None
        user_info = await context.bot.get_chat(user_id)
        username = user_info.username or user_info.full_name or "User"
        if last_menu_id:
            try:
                new_text, new_keyboard = utils.build_main_menu_message(user_id, username)
                await context.bot.edit_message_text(chat_id=user_id, message_id=last_menu_id, text=new_text, reply_markup=new_keyboard, parse_mode="Markdown")
            except Exception as e_edit:
                config.logger.warning(f"Gagal edit menu utama untuk user {user_id}, memanggil start: {e_edit}")
                from handlers.user_conversation import start
                class FakeUpdate: __init__ = lambda self, user, chat: setattr(self, 'effective_user', user) or setattr(self, 'message', None) or setattr(self, 'effective_chat', chat)
                await start(FakeUpdate(user_info, user_info), context)
        else:
            from handlers.user_conversation import start
            class FakeUpdate: __init__ = lambda self, user, chat: setattr(self, 'effective_user', user) or setattr(self, 'message', None) or setattr(self, 'effective_chat', chat)
            await start(FakeUpdate(user_info, user_info), context)
    except Exception as e:
        config.logger.error(f"Gagal notif pembelian/update menu ke user {user_id}: {e}")

# Di dalam file handlers/admin_callbacks.py
# Ganti seluruh fungsi ini

# Di dalam file handlers/admin_callbacks.py
# Ganti seluruh fungsi ini

# Di dalam file handlers/admin_callbacks.py
# GANTI SELURUH FUNGSI INI

async def confirm_payment_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Konfirmasi & Poin diproses...")
    unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not submission:
        return await query.edit_message_text("⚠️ Data submission tidak ditemukan.")
    
    user_id = submission['u_id']
    db.update_submission(unique_id, {"payment_status": "paid"})
    reward_diberikan = db.increment_and_check_reward(user_id)
    await query.edit_message_caption(f"✅ *Pembayaran untuk @{submission['u_name']} telah dikonfirmasi.*\n+1 Poin diberikan.", parse_mode="Markdown", reply_markup=None)
    post_keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("🚀 Post ke Channel", callback_data=f"post:{unique_id}")]])
    submission_msg_id = submission['submission_msg_id']
    if submission_msg_id:
        try:
            admin_caption = (f"<b>PEMBAYARAN LUNAS</b>\n\n{submission['pet_name']}\n\n"
                             f"User: {submission['user_tele']}\nOleh: @{submission['u_name']}\nID: <code>{unique_id}</code>")
            await context.bot.edit_message_caption(
                chat_id=config.ADMIN_GROUP_ID, message_id=submission_msg_id,
                caption=admin_caption, reply_markup=post_keyboard, parse_mode="HTML")
        except Exception as e:
            config.logger.error(f"Gagal edit pesan pengajuan asli {submission_msg_id}: {e}")
            
    # --- BLOK PENGHAPUSAN PESAN (BAGIAN PALING PENTING) ---
    try:
        # Hapus pesan QRIS dari bot
        if submission.get('bot_qris_msg_id'):
            await context.bot.delete_message(chat_id=user_id, message_id=submission['bot_qris_msg_id'])
        
        # Hapus pesan bukti transfer dari user
        if submission.get('user_proof_msg_id'):
            await context.bot.delete_message(chat_id=user_id, message_id=submission['user_proof_msg_id'])
            
        # Hapus pesan notifikasi "Pembayaran Terkirim..."
        if submission.get('user_notice_msg_id'):
            await context.bot.delete_message(chat_id=user_id, message_id=submission['user_notice_msg_id'])
            
    except Exception as e:
        config.logger.warning(f"Gagal menghapus salah satu pesan konfirmasi untuk user {user_id}: {e}")
    # --- AKHIR BLOK PENGHAPUSAN ---
    
    # Lanjutkan dengan notifikasi konfirmasi dan refresh menu
    try:
        notif_text = "✅ Pembayaran Anda telah dikonfirmasi. +1 Poin Reward ditambahkan. Pengajuan Anda akan segera diposting."
        if reward_diberikan: notif_text += "\n✨ *Selamat!* Anda mendapatkan 1 Tiket Reward Gratis!"
        sent_msg = await context.bot.send_message(user_id, notif_text, parse_mode="Markdown")
        context.job_queue.run_once(utils.delete_message_after_delay, 5, chat_id=user_id, data={'message_id': sent_msg.message_id})
        
        user_data = db.get_user_data(user_id)
        last_menu_id = user_data.get('last_menu_id') if user_data else None
        if last_menu_id:
            try:
                user_info = await context.bot.get_chat(user_id)
                username = user_info.username or user_info.full_name or "User"
                new_text, new_keyboard = utils.build_main_menu_message(user_id, username)
                await context.bot.edit_message_text(chat_id=user_id, message_id=last_menu_id, text=new_text, reply_markup=new_keyboard, parse_mode="Markdown")
            except Exception as e_edit:
                config.logger.warning(f"Gagal edit menu utama untuk user {user_id}, memanggil start: {e_edit}")
                from handlers.user_conversation import start
                user_info = await context.bot.get_chat(user_id)
                class FakeUpdate: __init__ = lambda self, user, chat: setattr(self, 'effective_user', user) or setattr(self, 'message', None) or setattr(self, 'effective_chat', chat)
                await start(FakeUpdate(user_info, user_info), context)
        else:
            from handlers.user_conversation import start
            user_info = await context.bot.get_chat(user_id)
            class FakeUpdate: __init__ = lambda self, user, chat: setattr(self, 'effective_user', user) or setattr(self, 'message', None) or setattr(self, 'effective_chat', chat)
            await start(FakeUpdate(user_info, user_info), context)
    except Exception as e:
        config.logger.error(f"Gagal proses notifikasi/update menu untuk user {user_id}: {e}")

# ==============================================================================
# --- FUNGSI POSTING & MANAJEMEN PENGAJUAN ---
# ==============================================================================

# Di dalam file: handlers/admin_callbacks.py
# Ganti seluruh fungsi ini

async def post_submission_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer("Memproses postingan...")
    unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not submission:
        await query.edit_message_caption(caption=f"❌ Gagal: Pengajuan ID `{unique_id}` tidak ditemukan.", parse_mode="Markdown")
        return
    
    try:
        # Langkah 1: Kirim Pesan Awal (Tidak ada perubahan di sini)
        channel_caption = (f"<b>#TITIP</b>\n<b>FOR SALE !!!</b>\n\n{submission['pet_name']}\n\n"
                           f"Note:\nPet ini bukan milik @kandangpet, disarankan menggunakan rekber.\n\n"
                           f"🛒 DM to order! : {submission['user_tele']}\n"
                           f"🚀 Subs Channel: @kandangpet\n💸 Payment: e-wallet/Avrek")
        
        user_tele = submission['user_tele'].strip()
        username = user_tele[1:] if user_tele.startswith('@') else (user_tele.split('t.me/')[-1] if 't.me/' in user_tele else user_tele)
        
        keyboard_awal = InlineKeyboardMarkup([
            [InlineKeyboardButton("🛒 DM Seller", url=f"https://t.me/{username}")],
            [InlineKeyboardButton("📝 Mau Jastip Juga?", url=f"https://t.me/{context.bot.username}")]
        ])

        posted_message = await context.bot.send_photo(
            chat_id=config.TARGET_POST_CHAT,
            photo=submission['photo_file_id'],
            caption=channel_caption,
            reply_markup=keyboard_awal,
            parse_mode="HTML"
        )
        
        # --- LANGKAH 2 (DIPERBARUI & LEBIH CANGGIH) ---
        # Membuat link secara manual agar berfungsi untuk channel publik DAN pribadi
        
        post_link = ""
        if posted_message.chat.username:
            # Jika channel publik, gunakan username
            post_link = f"https://t.me/{posted_message.chat.username}/{posted_message.message_id}"
        else:
            # Jika channel pribadi, bangun link secara manual
            # Menghilangkan prefix -100 dari chat_id
            chat_id_for_link = str(posted_message.chat.id).replace("-100", "", 1)
            post_link = f"https://t.me/c/{chat_id_for_link}/{posted_message.message_id}"

        # Simpan link yang sudah benar ke DB
        db.update_submission(unique_id, {"status": "on sale", "post_link": post_link})

        # --- LANGKAH 3 (Tidak ada perubahan) ---
        # Edit Pesan untuk Tambah Tombol "Cek Postingan"
        first_row = [InlineKeyboardButton("🛒 DM Seller", url=f"https://t.me/{username}")]
        first_row.append(InlineKeyboardButton("🔗 Cek Postingan", url=post_link))
        keyboard_final = InlineKeyboardMarkup([
            first_row,
            [InlineKeyboardButton("📝 Mau Jastip Juga?", url=f"https://t.me/{context.bot.username}")]
        ])
        await context.bot.edit_message_reply_markup(
            chat_id=config.TARGET_POST_CHAT,
            message_id=posted_message.message_id,
            reply_markup=keyboard_final
        )

    except Exception as e:
        config.logger.error(f"Gagal posting ke channel untuk ID {unique_id}: {e}")
        await query.edit_message_caption(caption=f"❌ Gagal posting ke channel. Error: {e}")
        return

    # --- Sisa kode untuk notifikasi dan update pesan admin tidak perlu diubah ---
    user_id = submission['u_id'] if 'u_id' in submission else None
    if user_id:
        try:
            pet_preview = " ".join(submission['pet_name'].split()[:7]) + "..."
            notification_text = (f"✅ *Postingan Berhasil!*\nJastip Anda untuk *\"{pet_preview}\"* telah diposting.")
            intro_msg = await context.bot.send_message(user_id, notification_text, parse_mode="Markdown")
            context.job_queue.run_once(utils.delete_message_after_delay, 5, chat_id=user_id, data={'message_id': intro_msg.message_id})
            user_data_live = db.get_user_data(user_id)
            last_menu_id = user_data_live.get('last_menu_id') if user_data_live else None
            if last_menu_id:
                user_info = await context.bot.get_chat(user_id)
                username = user_info.username or user_info.full_name or "User"
                new_text, new_keyboard = utils.build_main_menu_message(user_id, username)
                await context.bot.edit_message_text(chat_id=user_id, message_id=last_menu_id, text=new_text, reply_markup=new_keyboard, parse_mode="Markdown")
        except Exception as e:
            config.logger.error(f"Gagal notif/refresh menu untuk user {user_id} setelah posting: {e}")

    original_admin_caption = query.message.caption_html
    final_caption = f"{original_admin_caption}\n\n✅ <b>Berhasil Diposting ke Channel.</b>"
    await query.edit_message_caption(
        caption=final_caption,
        parse_mode="HTML",
        reply_markup=None
    )

async def admin_menu_submission_management(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    text = "📂 *Manajemen Pengajuan*\n\nPilih aksi di bawah ini untuk mengelola pengajuan."
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("⏳ Lihat Pengajuan Pending", callback_data="list_pending:0")],
        [InlineKeyboardButton("✏️ Edit Pengajuan User", callback_data="list_editable:0")],
        [InlineKeyboardButton("🗑️ Hapus Postingan Aktif", callback_data="list_active:0")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back_main")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_list_pending_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    page = int(query.data.split(':')[1])
    items_per_page = 5
    all_items = db.db_execute("SELECT * FROM submissions WHERE status = 'pending' AND payment_status = 'unpaid' ORDER BY timestamp ASC", fetchall=True)
    if not all_items:
        return await query.edit_message_text("✅ Tidak ada pengajuan yang menunggu pembayaran saat ini.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")]]))
    total_pages = (len(all_items) + items_per_page - 1) // items_per_page
    paginated_items = all_items[page * items_per_page:(page + 1) * items_per_page]
    text = f"⏳ *Pengajuan Pending* (Hal {page + 1}/{total_pages}):"
    keyboard_rows = [[InlineKeyboardButton(f"@{item['u_name']} - \"{item['pet_name'][:20]}...\"", callback_data=f"view_pending:{item['unique_id']}")] for item in paginated_items]
    nav = [InlineKeyboardButton("<<", callback_data=f"list_pending:{page-1}") if page > 0 else None,
           InlineKeyboardButton(">>", callback_data=f"list_pending:{page+1}") if page < total_pages - 1 else None]
    keyboard_rows.append([b for b in nav if b])
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="Markdown")

async def admin_view_pending_submission_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not submission:
        return await query.edit_message_text("❌ Pengajuan tidak ditemukan.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="list_pending:0")]]))
    await query.message.delete()
    caption = (f"<b>Detail Pengajuan Pending</b>\n\n"
               f"<b>Dari:</b> @{submission['u_name']} (<code>{submission['u_id']}</code>)\n"
               f"<b>Kontak:</b> {submission['user_tele']}\n"
               f"<b>ID Pengajuan:</b> <code>{unique_id}</code>\n"
               f"------------------------------------\n"
               f"{submission['pet_name']}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Konfirmasi Pembayaran", callback_data=f"confirm_payment:{unique_id}")],
        [InlineKeyboardButton("❌ Tolak & Hapus", callback_data=f"reject_submission:{unique_id}")],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar", callback_data="list_pending:0")]
    ])
    await context.bot.send_photo(query.from_user.id, submission['photo_file_id'], caption=caption, parse_mode="HTML", reply_markup=keyboard)

async def admin_reject_submission(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menolak pengajuan, lalu membangun ulang dan mengirim daftar pending."""
    query = update.callback_query
    await query.answer("Menolak pengajuan...")

    unique_id = query.data.split(":")[1]
    
    # Simpan data user sebelum dihapus (untuk notifikasi)
    submission_for_notif = db.get_submission_by_id(unique_id)
    
    # Ubah status di DB
    db.update_submission(unique_id, {"status": "rejected", "payment_status": "rejected"})
    
    # Kirim notifikasi ke user (jika data ditemukan)
    if submission_for_notif:
        try:
            pet_preview = " ".join(submission_for_notif['pet_name'].split()[:7]) + "..."
            notif_text = f"❌ Pengajuan Anda untuk *\"{pet_preview}\"* telah ditolak oleh admin."
            await context.bot.send_message(submission_for_notif['u_id'], notif_text, parse_mode="Markdown")
        except Exception as e:
            config.logger.warning(f"Gagal kirim notif penolakan ke user {submission_for_notif['u_id']}: {e}")

    # Hapus pesan detail view yang lama
    try:
        await query.message.delete()
    except Exception:
        pass

    # Kirim pesan konfirmasi sementara ke admin
    confirm_msg = await context.bot.send_message(query.from_user.id, "✅ Pengajuan telah ditolak. Memuat ulang daftar...")
    context.job_queue.run_once(utils.delete_message_after_delay, 2, chat_id=query.from_user.id, data={'message_id': confirm_msg.message_id})

    # --- BAGIAN BARU: Bangun ulang daftar pending secara manual ---
    page = 0 # Selalu kembali ke halaman pertama
    items_per_page = 5
    all_items = db.db_execute(
        "SELECT * FROM submissions WHERE status = 'pending' AND payment_status = 'unpaid' ORDER BY timestamp ASC",
        fetchall=True
    )

    if not all_items:
        text = "✅ Tidak ada lagi pengajuan yang menunggu pembayaran."
        keyboard = InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")]])
        await context.bot.send_message(query.from_user.id, text, reply_markup=keyboard, parse_mode="Markdown")
        return

    total_pages = (len(all_items) + items_per_page - 1) // items_per_page
    paginated_items = all_items[page * items_per_page:(page + 1) * items_per_page]

    text = f"⏳ *Pengajuan Pending* (Hal {page + 1}/{total_pages}):"
    keyboard_rows = [
        [InlineKeyboardButton(f"@{item['u_name']} - \"{item['pet_name'][:20]}...\"", callback_data=f"view_pending:{item['unique_id']}")]
        for item in paginated_items
    ]
    
    nav_buttons = []
    if page > 0:
        nav_buttons.append(InlineKeyboardButton("<<", callback_data=f"list_pending:{page-1}"))
    if page < total_pages - 1:
        nav_buttons.append(InlineKeyboardButton(">>", callback_data=f"list_pending:{page+1}"))
    if nav_buttons:
        keyboard_rows.append(nav_buttons)
        
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")])
    
    # Kirim daftar pending sebagai pesan baru
    await context.bot.send_message(
        chat_id=query.from_user.id,
        text=text,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
        parse_mode="Markdown"
    )

# ==============================================================================
# --- PENGATURAN BOT ---
# ==============================================================================

async def admin_menu_settings(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    maintenance_mode = db.get_setting('maintenance_mode', 'off')
    status_text = "🔴 NONAKTIF (Mode Perbaikan)" if maintenance_mode == 'on' else "🟢 AKTIF"
    button_text = "✨ Nonaktifkan Mode Perbaikan" if maintenance_mode == 'on' else "🔧 Aktifkan Mode Perbaikan"
    text = (f"⚙️ *Pengaturan Bot*\n\n"
            f"Status Bot untuk Pengguna: *{status_text}*\n\n"
            "Saat Mode Perbaikan aktif, pengguna biasa tidak akan bisa memulai submit baru atau menggunakan bot. Admin tetap bisa mengakses semua fitur.")
    keyboard = InlineKeyboardMarkup([[InlineKeyboardButton(button_text, callback_data="toggle_maintenance")],
                                     [InlineKeyboardButton("⬅️ Kembali", callback_data="admin_back_main")]])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_toggle_maintenance_mode(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer("Mengubah status...")
    current_mode = db.get_setting('maintenance_mode', 'off')
    new_mode = 'on' if current_mode == 'off' else 'off'
    db.set_setting('maintenance_mode', new_mode)
    await admin_menu_settings(update, context)

# ==============================================================================
# --- MANAJEMEN PENGGUNA (EDIT, BAN, DLL) ---
# ==============================================================================

async def admin_choose_user_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    _, action, page_str = query.data.split(':')
    page = int(page_str)
    users_per_page = 5
    all_users = db.db_execute("SELECT u_id FROM user_rewards ORDER BY u_id DESC", fetchall=True)
    if not all_users:
        return await query.edit_message_text("Belum ada pengguna terdaftar.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_user")]]))
    total_pages = (len(all_users) + users_per_page - 1) // users_per_page
    paginated_users = all_users[page * users_per_page:(page + 1) * users_per_page]
    text = f"👤 *Pilih Pengguna* (Hal {page + 1}/{total_pages}):"
    keyboard_rows = []
    for user_row in paginated_users:
        u_id = user_row['u_id']
        latest_submission = db.db_execute("SELECT u_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 1", (u_id,), fetchone=True)
        u_name = latest_submission['u_name'] if latest_submission else f"ID_{u_id}"
        keyboard_rows.append([InlineKeyboardButton(f"@{u_name} ({u_id})", callback_data=f"admin_manage_user:{u_id}")])
    nav = [InlineKeyboardButton("<<", callback_data=f"admin_choose_user:{action}:{page-1}") if page > 0 else None,
           InlineKeyboardButton(">>", callback_data=f"admin_choose_user:{action}:{page+1}") if page < total_pages - 1 else None]
    keyboard_rows.append([b for b in nav if b])
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_user")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="Markdown")

async def admin_user_management_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    _, user_id_str = query.data.split(':')
    target_id = int(user_id_str)
    context.chat_data['admin_target_uid'] = target_id
    user_data = db.get_user_data(target_id)
    user_name = db.db_execute("SELECT u_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 1", (target_id,), fetchone=True)
    target_name = user_name['u_name'] if user_name else f"ID_{target_id}"
    text = f"👤 Mengelola Pengguna: *@{target_name}* (`{target_id}`)\n\nPilih tindakan:"
    is_banned = user_data and user_data.get('is_banned')
    ban_button = InlineKeyboardButton("✅ Unban User", callback_data=f"admin_confirm_unban:{target_id}") if is_banned else InlineKeyboardButton("🚫 Ban User", callback_data=f"admin_confirm_ban:{target_id}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Lihat Info Lengkap", callback_data=f"admin_info_user:{target_id}")],
        [InlineKeyboardButton("✏️ Edit Kuota & Poin", callback_data=f"admin_edit_quota_menu:{target_id}")],
        [ban_button],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar User", callback_data="admin_choose_user:info:0")]
    ])
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_info_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    _, target_id_str = query.data.split(':')
    target_id = int(target_id_str)
    user_submission_data = db.db_execute("SELECT u_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 1", (target_id,), fetchone=True)
    target_name = user_submission_data['u_name'] if user_submission_data else f"ID_{target_id}"
    user_data = db.get_user_data(target_id) or {}
    submissions = db.db_execute("SELECT status, pet_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 5", (target_id,), fetchall=True)
    history_text = "\n".join([f"- `{s['status'].upper()}`: {s['pet_name'][:30]}..." for s in submissions]) if submissions else "Belum ada."
    kuota_texts = []
    if user_data.get('available_rewards', 0) > 0: kuota_texts.append(f"  - 🎁 Tiket Reward: *{user_data['available_rewards']}*")
    if user_data.get('paket_dasar_posts', 0) > 0: kuota_texts.append(f"  - 🎟️ Kuota Dasar: *{user_data['paket_dasar_posts']}*")
    if user_data.get('paket_hemat_posts', 0) > 0: kuota_texts.append(f"  - 🎟️ Kuota Hemat: *{user_data['paket_hemat_posts']}*")
    if user_data.get('paket_sultan_posts', 0) > 0: kuota_texts.append(f"  - 👑 Kuota Sultan: *{user_data['paket_sultan_posts']}*")
    kuota_info = "\n".join(kuota_texts) if kuota_texts else "Tidak ada."
    info_text = (f"ℹ️ *Detail Pengguna*\n"
                 f"👤 `@{target_name}` (`{target_id}`)\n\n"
                 f"📈 Poin Reward Saat Ini: *{user_data.get('submission_count', 0)}* / 5\n"
                 f"🚫 Status Ban: *{'YA' if user_data.get('is_banned') else 'TIDAK'}*\n\n"
                 f"🛍️ *Sisa Kuota:*\n{kuota_info}\n\n"
                 f"📜 *5 Riwayat Terakhir:*\n{history_text}")
    await query.edit_message_text(info_text, parse_mode="Markdown",
        reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data=f"admin_manage_user:{target_id}")]]))

async def admin_confirm_action_callback(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    parts = query.data.split(':')
    action = parts[0].split('_')[-1]
    target_id = int(parts[1])
    user_submission_data = db.db_execute("SELECT u_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 1", (target_id,), fetchone=True)
    target_name = user_submission_data['u_name'] if user_submission_data else f"ID_{target_id}"
    message_text = "❌ Aksi tidak diketahui."
    if action == 'ban':
        db.db_execute("INSERT OR IGNORE INTO user_rewards (u_id) VALUES (%s)", (target_id,))
        db.db_execute("UPDATE user_rewards SET is_banned = 1 WHERE u_id = %s", (target_id,))
        message_text = f"🚫 Pengguna `@{target_name}` telah di-BAN."
    elif action == 'unban':
        db.db_execute("UPDATE user_rewards SET is_banned = 0 WHERE u_id = %s", (target_id,))
        message_text = f"✅ Pengguna `@{target_name}` telah di-UNBAN."
    await query.edit_message_text(message_text, parse_mode="Markdown")
    await asyncio.sleep(2)
    await admin_menu_user(update, context)

async def admin_edit_quota_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu untuk memilih TIPE item yang akan diedit (Kuota/Tiket/Poin)."""
    query = update.callback_query
    await query.answer()
    
    _, user_id_str = query.data.split(':')
    
    text = "✏️ *Edit Kuota & Poin*\n\nPilih item yang ingin Anda ubah:"
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("🎟️ Edit Kuota Paket", callback_data=f"edit_type:kuota:{user_id_str}")],
        [InlineKeyboardButton("🎁 Edit Tiket Reward", callback_data=f"edit_type:reward:{user_id_str}")],
        [InlineKeyboardButton("🎯 Edit Poin Reward", callback_data=f"edit_type:poin:{user_id_str}")],
        [InlineKeyboardButton("⬅️ Kembali", callback_data=f"admin_manage_user:{user_id_str}")]
    ])
    await query.message.edit_text(text, reply_markup=keyboard, parse_mode="Markdown")

async def admin_choose_action_menu(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Menampilkan menu untuk memilih AKSI (Tambah/Kurang)."""
    query = update.callback_query
    await query.answer()

    _, item_type, user_id_str = query.data.split(':')
    
    item_name_map = {
        "kuota": "Kuota Paket",
        "reward": "Tiket Reward",
        "poin": "Poin Reward"
    }
    item_name = item_name_map.get(item_type, "Item")

    text = f"Pilih tindakan untuk *{item_name}*:"
    keyboard = InlineKeyboardMarkup([
        [
            InlineKeyboardButton(f"➕ Tambah", callback_data=f"edit_start:add_{item_type}:{user_id_str}"),
            InlineKeyboardButton(f"➖ Kurangi", callback_data=f"edit_start:sub_{item_type}:{user_id_str}")
        ],
        [InlineKeyboardButton("⬅️ Kembali", callback_data=f"admin_edit_quota_menu:{user_id_str}")]
    ])
    await query.edit_message_text(text, reply_markup=keyboard, parse_mode="Markdown")

# --- Fitur Manajemen Pengajuan (Edit/Hapus) ---

async def admin_list_editable_submissions(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    page = int(query.data.split(':')[1])
    items_per_page = 5
    all_items = db.db_execute("SELECT * FROM submissions WHERE status IN ('pending', 'on sale') ORDER BY timestamp ASC", fetchall=True)
    if not all_items:
        return await query.edit_message_text("✅ Tidak ada pengajuan yang bisa diedit saat ini.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")]]))
    total_pages = (len(all_items) + items_per_page - 1) // items_per_page
    paginated_items = all_items[page * items_per_page:(page + 1) * items_per_page]
    text = f"✏️ *Pilih Pengajuan untuk Diedit* (Hal {page + 1}/{total_pages}):"
    keyboard_rows = [[InlineKeyboardButton(f"@{item['u_name']} - {item['pet_name'][:20]}...", callback_data=f"view_editable:{item['unique_id']}")] for item in paginated_items]
    nav = [InlineKeyboardButton("<<", callback_data=f"list_editable:{page-1}") if page > 0 else None,
           InlineKeyboardButton(">>", callback_data=f"list_editable:{page+1}") if page < total_pages - 1 else None]
    keyboard_rows.append([b for b in nav if b])
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="Markdown")

async def admin_view_editable_submission_detail(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not submission: return await query.edit_message_text("❌ Pengajuan tidak ditemukan.")
    try: await query.message.delete()
    except: pass
    context.chat_data['admin_edit_id'] = unique_id
    caption = (f"<b>Detail Pengajuan</b>\n\nID: <code>{unique_id}</code>\n"
               f"Dari: @{submission['u_name']}\n\n<b>Deskripsi Saat Ini:</b>\n{submission['pet_name']}\n\n"
               f"<b>Kontak Saat Ini:</b>\n<code>{submission['user_tele']}</code>\n\n"
               "Pilih bagian yang ingin diubah:")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✏️ Edit Deskripsi", callback_data="admin_edit_desc")],
        [InlineKeyboardButton("👤 Edit Kontak", callback_data="admin_edit_tele")],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar", callback_data="list_editable:0")]
    ])
    await context.bot.send_photo(query.message.chat.id, submission['photo_file_id'], caption, parse_mode="HTML", reply_markup=keyboard)
    return ConversationHandler.END

async def admin_prompt_for_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    query = update.callback_query; action = query.data.split('_')[-1]; await query.answer()
    if action == 'desc': text, state = "📝 Silakan kirim *deskripsi baru*.", K.STATE_ADMIN_EDIT_DESC_INPUT
    else: text, state = "👤 Silakan kirim *kontak user baru*.", K.STATE_ADMIN_EDIT_TELE_INPUT
    await query.message.delete()
    msg = await context.bot.send_message(query.message.chat.id, text, parse_mode="Markdown")
    context.chat_data['last_bot_message_id'] = msg.message_id
    return state

async def admin_list_active_posts(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; await query.answer()
    page = int(query.data.split(':')[1])
    items_per_page = 5
    all_items = db.db_execute("SELECT * FROM submissions WHERE status = 'on sale' ORDER BY timestamp DESC", fetchall=True)
    if not all_items:
        return await query.edit_message_text("✅ Tidak ada postingan aktif saat ini.", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")]]))
    total_pages = (len(all_items) + items_per_page - 1) // items_per_page
    paginated_items = all_items[page * items_per_page:(page + 1) * items_per_page]
    text = f"🗑️ *Pilih Postingan untuk Dihapus* (Hal {page + 1}/{total_pages}):"
    keyboard_rows = [[InlineKeyboardButton(f"@{item['u_name']} - {item['pet_name'][:20]}...", callback_data=f"confirm_delete:{item['unique_id']}")] for item in paginated_items]
    nav = [InlineKeyboardButton("<<", callback_data=f"list_active:{page-1}") if page > 0 else None,
           InlineKeyboardButton(">>", callback_data=f"list_active:{page+1}") if page < total_pages - 1 else None]
    keyboard_rows.append([b for b in nav if b])
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali", callback_data="admin_menu_submission")])
    await query.edit_message_text(text, reply_markup=InlineKeyboardMarkup(keyboard_rows), parse_mode="Markdown")

async def admin_confirm_delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not submission or not submission['post_link']:
        return await query.answer("❌ Gagal, postingan tidak valid.", show_alert=True)
    await query.message.delete()
    caption = ("⚠️ Anda yakin ingin menghapus postingan ini secara permanen dari channel?\n\n"
               f"<b>ID:</b> <code>{unique_id}</code>\n"
               f"<b>Post:</b> {submission['pet_name'][:50]}...")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ya, Hapus Permanen", callback_data=f"execute_delete:{unique_id}")],
        [InlineKeyboardButton("🚫 Batal", callback_data="list_active:0")]
    ])
    await context.bot.send_photo(query.message.chat.id, submission['photo_file_id'], caption, parse_mode="HTML", reply_markup=keyboard)

async def admin_execute_delete_post(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query; unique_id = query.data.split(":")[1]
    submission = db.get_submission_by_id(unique_id)
    if not submission or not submission['post_link']:
        return await query.edit_message_caption("❌ Gagal, postingan tidak valid.")
    try:
        msg_id = int(submission['post_link'].split('/')[-1])
        await context.bot.delete_message(config.TARGET_POST_CHAT, msg_id)
    except Exception as e:
        await query.answer(f"⚠️ Gagal hapus dari channel: {e}", show_alert=True)
    db.update_submission(unique_id, {"status": "deleted_by_admin"})
    await query.edit_message_caption("✅ Postingan telah dihapus.", reply_markup=None)
    await asyncio.sleep(2)
    query.data = "list_active:0"
    await admin_list_active_posts(update, context)