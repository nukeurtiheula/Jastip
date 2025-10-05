import asyncio
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import ContextTypes, ConversationHandler
import database as db
import constants as K
import utils
import config
from handlers.admin_callbacks import admin_panel
from .admin_callbacks import admin_view_editable_submission_detail
from .admin_callbacks import admin_user_management_menu
from .admin_callbacks import admin_panel

# ==============================================================================
# --- ALUR BROADCAST PESAN ---
# ==============================================================================

async def admin_broadcast_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai alur broadcast pesan ke semua pengguna."""
    query = update.callback_query
    await query.answer()
    await query.edit_message_text("📢 Silakan kirim pesan yang ingin di-broadcast.\n\nKetik /cancel untuk batal.")
    context.chat_data['last_bot_message_id'] = query.message.message_id
    return K.STATE_ADMIN_GET_BROADCAST_MSG

async def admin_broadcast_get_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangkap pesan untuk broadcast dan meminta konfirmasi."""
    context.chat_data['broadcast_message'] = update.message
    total_users = len(db.db_execute("SELECT DISTINCT u_id FROM user_rewards", fetchall=True))
    
    await update.message.reply_text(
        f"⚠️ *KONFIRMASI BROADCAST*\nPesan di atas akan dikirim ke *{total_users}* pengguna. Proses ini tidak bisa dihentikan.\n\nYakin?",
        reply_markup=InlineKeyboardMarkup([
            [InlineKeyboardButton("✅ Ya, Kirim!", callback_data="admin_broadcast_confirm")],
            [InlineKeyboardButton("🚫 Batal", callback_data="admin_broadcast_cancel")]
        ]), parse_mode="Markdown")
    return ConversationHandler.END

async def admin_broadcast_confirm(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Mengeksekusi pengiriman broadcast."""
    query = update.callback_query
    broadcast_message = context.chat_data.pop('broadcast_message', None)
    
    if not broadcast_message:
        return await query.edit_message_text("❌ Gagal, pesan broadcast tidak ditemukan.")

    await query.edit_message_text(f"🚀 Memulai broadcast...")
    
    users = db.db_execute("SELECT DISTINCT u_id FROM user_rewards", fetchall=True)
    success, fail = 0, 0
    for user in users:
        try:
            await broadcast_message.copy(chat_id=user['u_id'])
            success += 1
        except Exception as e:
            config.logger.error(f"Gagal broadcast ke user {user['u_id']}: {e}")
            fail += 1
        await asyncio.sleep(0.1)
        
    await query.message.reply_text(f"🏁 *Broadcast Selesai!*\n✅ Terkirim: *{success}*\n❌ Gagal: *{fail}*", parse_mode="Markdown")
    await admin_panel(update, context)

async def admin_broadcast_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Membatalkan alur broadcast."""
    query = update.callback_query
    context.chat_data.pop('broadcast_message', None)
    await query.edit_message_text("ℹ️ Broadcast dibatalkan.")
    await admin_panel(update, context)

# ==============================================================================
# --- ALUR PENCARIAN PENGGUNA ---
# ==============================================================================
# (Jika Anda ingin mengaktifkan kembali fitur "Cari User", gunakan kode ini)
# (Saat ini, fitur ini belum diaktifkan di menu admin untuk penyederhanaan)

async def admin_search_user_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memulai alur pencarian, meminta input username dari admin."""
    query = update.callback_query
    await query.answer()
    
    await query.edit_message_text(
        "🔍 Masukkan *username* (@username) atau bagian dari username yang ingin dicari.\n\nKetik /cancel untuk kembali.",
        parse_mode="Markdown"
    )
    # Simpan ID pesan agar bisa dihapus nanti
    context.chat_data['last_bot_message_id'] = query.message.message_id
    
    return K.STATE_ADMIN_SEARCH_USER_INPUT

async def admin_search_user_handler(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangani input username, mencari di DB, dan menampilkan hasil."""
    user_input = update.message.text.strip().lstrip('@')
    
    # Cari semua user unik yang cocok dengan input
    users = db.db_execute(
        "SELECT DISTINCT u_id, u_name FROM submissions WHERE u_name LIKE %s",
        (f'%{user_input}%',),
        fetchall=True
    )

    # --- Membersihkan chat ---
    try:
        await update.message.delete() # Hapus pesan input dari admin
    except:
        pass
    if last_msg_id := context.chat_data.pop('last_bot_message_id', None):
        try:
            # Hapus pesan prompt "Masukkan username..." dari bot
            await context.bot.delete_message(update.effective_chat.id, last_msg_id)
        except:
            pass

    # --- Menampilkan hasil ---
    if not users:
        msg = await context.bot.send_message(update.effective_chat.id, "❌ Tidak ada pengguna yang cocok ditemukan.")
        await asyncio.sleep(2)
        await msg.delete()
        await admin_panel(update, context) # Kembali ke menu utama admin
        return ConversationHandler.END
        
    text = "✅ *Hasil Pencarian:*\nPilih pengguna untuk dikelola:"
    
    # Buat tombol untuk setiap hasil, arahkan ke menu hub manajemen
    keyboard_rows = [
        [InlineKeyboardButton(f"@{user['u_name']} ({user['u_id']})", callback_data=f"admin_manage_user:{user['u_id']}")]
        for user in users
    ]
    keyboard_rows.append([InlineKeyboardButton("⬅️ Kembali ke Menu User", callback_data="admin_menu_user")])
    
    await context.bot.send_message(
        update.effective_chat.id,
        text,
        reply_markup=InlineKeyboardMarkup(keyboard_rows),
        parse_mode="Markdown"
    )
    return ConversationHandler.END

# ==============================================================================
# --- FUNGSI PEMBATALAN ADMIN ---
# ==============================================================================

async def admin_cancel(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan alur percakapan admin dan kembali ke menu."""
    try: 
        if update.message: await update.message.delete()
    except Exception: pass
        
    if last_bot_msg_id := context.chat_data.pop('last_bot_message_id', None):
        try:
            await context.bot.delete_message(update.effective_chat.id, last_bot_msg_id)
        except Exception: pass
            
    # Hapus sisa data sesi admin
    keys_to_clear = [key for key in context.chat_data if key.startswith('admin_')]
    for key in keys_to_clear: context.chat_data.pop(key)

    msg = await context.bot.send_message(update.effective_chat.id, "ℹ️ Aksi dibatalkan.")
    await admin_panel(update, context)
    context.job_queue.run_once(utils.delete_message_after_delay, 2, chat_id=update.effective_chat.id, data={'message_id': msg.message_id})
    
    return ConversationHandler.END


# ==============================================================================
# --- ALUR EDIT PENGAJUAN ---
# ==============================================================================

async def admin_get_new_desc(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangkap deskripsi baru dari admin dan mengupdate DB."""
    query = update.callback_query
    new_desc = update.message.text_html
    unique_id = context.chat_data.get('admin_edit_id')

    if not unique_id:
        await update.message.reply_text("❌ Sesi edit tidak valid. Harap ulangi.")
        return ConversationHandler.END

    db.update_submission(unique_id, {"pet_name": new_desc})
    await update.message.reply_text("✅ Deskripsi berhasil diupdate.")
    
    # Hapus pesan prompt lama
    if last_msg_id := context.chat_data.pop('last_bot_message_id', None):
        try: await context.bot.delete_message(update.effective_chat.id, last_msg_id)
        except: pass
    
    # Tampilkan kembali detail yang sudah terupdate
    fake_query = type('FakeQuery', (), {'data': f"view_editable:{unique_id}", 'answer': (lambda: None), 'message': update.message})()
    await admin_view_editable_submission_detail(type('FakeUpdate', (), {'callback_query': fake_query})(), context)
    return ConversationHandler.END

async def admin_get_new_tele(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangkap kontak/tele baru dari admin dan mengupdate DB."""
    new_tele = update.message.text.strip()
    unique_id = context.chat_data.get('admin_edit_id')

    if not unique_id:
        await update.message.reply_text("❌ Sesi edit tidak valid. Harap ulangi.")
        return ConversationHandler.END

    db.update_submission(unique_id, {"user_tele": new_tele})
    await update.message.reply_text("✅ Kontak user berhasil diupdate.")

    # Hapus pesan prompt lama
    if last_msg_id := context.chat_data.pop('last_bot_message_id', None):
        try: await context.bot.delete_message(update.effective_chat.id, last_msg_id)
        except: pass

    # Tampilkan kembali detail yang sudah terupdate
    fake_query = type('FakeQuery', (), {'data': f"view_editable:{unique_id}", 'answer': (lambda: None), 'message': update.message})()
    await admin_view_editable_submission_detail(type('FakeUpdate', (), {'callback_query': fake_query})(), context)
    return ConversationHandler.END


# ==============================================================================
# --- ALUR EDIT KUOTA & POIN PENGGUNA ---
# ==============================================================================

async def ask_for_package_type(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Meminta admin memilih jenis paket yang akan diubah."""
    query = update.callback_query; await query.answer()
    _, action, user_id_str = query.data.split(':')
    context.chat_data['admin_edit_action'] = action
    context.chat_data['admin_edit_target_uid'] = int(user_id_str)
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("Dasar", callback_data="edit_pkg:dasar"), InlineKeyboardButton("Hemat", callback_data="edit_pkg:hemat"), InlineKeyboardButton("Sultan", callback_data="edit_pkg:sultan")],
        [InlineKeyboardButton("🚫 Batal", callback_data="admin_edit_cancel")]])
    await query.edit_message_text("Pilih jenis paket kuota yang ingin diubah:", reply_markup=keyboard)
    return K.STATE_ADMIN_CHOOSE_PKG_TYPE

async def ask_for_amount(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Meminta admin memasukkan jumlah dengan pesan yang spesifik."""
    query = update.callback_query; await query.answer()
    
    if query.data.startswith("edit_pkg:"):
        context.chat_data['admin_edit_pkg_type'] = query.data.split(':')[1]
    else:
        _, action, user_id_str = query.data.split(':')
        context.chat_data['admin_edit_action'] = action
        context.chat_data['admin_edit_target_uid'] = int(user_id_str)

    action_text_map = {
        "add_kuota": "ditambahkan", "sub_kuota": "dikurangi",
        "add_reward": "ditambahkan", "sub_reward": "dikurangi",
        "add_poin": "ditambahkan", "sub_poin": "dikurangi",
    }
    item_name_map = {
        "kuota": f"kuota paket *{context.chat_data.get('admin_edit_pkg_type', '').title()}*",
        "reward": "tiket reward", "poin": "poin reward"
    }
    action_verb = action_text_map.get(context.chat_data['admin_edit_action'])
    item_name = item_name_map.get(context.chat_data['admin_edit_action'].split('_')[-1])

    await query.edit_message_text(f"Masukkan jumlah *{item_name}* yang ingin *{action_verb}*:", parse_mode="Markdown")
    return K.STATE_ADMIN_GET_EDIT_AMOUNT

async def ask_for_confirmation(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Menangkap jumlah, menghitung, dan meminta konfirmasi dari admin."""
    try:
        amount = int(update.message.text)
        if amount < 0: raise ValueError
    except (ValueError, TypeError):
        await update.message.reply_text("⚠️ Harap masukkan angka positif yang valid.")
        return K.STATE_ADMIN_GET_EDIT_AMOUNT

    context.chat_data['admin_edit_amount'] = amount
    action = context.chat_data.get('admin_edit_action')
    user_id = context.chat_data.get('admin_edit_target_uid')
    pkg_type = context.chat_data.get('admin_edit_pkg_type')
    
    user_data = db.get_user_data(user_id) or {}
    
    # Menghitung perubahan
    old_value, new_value = 0, 0
    item_name = ""
    if action in ["add_kuota", "sub_kuota"]:
        field = f"paket_{pkg_type}_posts"; item_name = f"Kuota {pkg_type.title()}"
        old_value = user_data.get(field, 0)
        new_value = old_value + amount if action == "add_kuota" else max(0, old_value - amount)
    elif action in ["add_reward", "sub_reward"]:
        item_name = "Tiket Reward"
        old_value = user_data.get('available_rewards', 0)
        new_value = old_value + amount if action == "add_reward" else max(0, old_value - amount)
    elif action in ["add_poin", "sub_poin"]:
        item_name = "Poin Reward"
        old_value = user_data.get('submission_count', 0)
        # Perhitungan poin tidak langsung, hanya untuk preview
        temp_new_points = old_value + amount if action == "add_poin" else old_value - amount
        new_value = max(0, temp_new_points)

    confirm_text = (
        f"⚠️ *KONFIRMASI PERUBAHAN*\n\n"
        f"Anda akan mengubah *{item_name}* untuk user `{user_id}`.\n\n"
        f"Nilai Awal: *{old_value}*\n"
        f"Nilai Akhir: *{new_value}*\n\n"
        "Apakah Anda yakin ingin melanjutkan?"
    )
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("✅ Ya, Lanjutkan", callback_data="confirm_edit_yes")],
        [InlineKeyboardButton("🚫 Batal", callback_data="admin_edit_cancel")]
    ])
    await update.message.reply_text(confirm_text, reply_markup=keyboard, parse_mode="Markdown")
    return K.STATE_ADMIN_CONFIRM_EDIT

async def execute_amount_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Mengeksekusi perubahan, me-refresh UI, dan membersihkan sesi."""
    query = update.callback_query
    await query.answer("Memproses...")
    
    amount = context.chat_data.get('admin_edit_amount')
    action = context.chat_data.get('admin_edit_action')
    user_id = context.chat_data.get('admin_edit_target_uid')
    pkg_type = context.chat_data.get('admin_edit_pkg_type')

    # Update Database
    if action in ["add_kuota", "sub_kuota"]:
        field = f"paket_{pkg_type}_posts"; operator = "+" if action == "add_kuota" else "-"
        db.db_execute(f"UPDATE user_rewards SET {field} = MAX(0, {field} {operator} %s) WHERE u_id = %s", (amount, user_id))
    elif action in ["add_reward", "sub_reward"]:
        operator = "+" if action == "add_reward" else "-"
        db.db_execute(f"UPDATE user_rewards SET available_rewards = MAX(0, available_rewards {operator} %s) WHERE u_id = %s", (amount, user_id))
    elif action in ["add_poin", "sub_poin"]:
        points_to_change = amount if action == "add_poin" else -amount
        db.increment_and_check_reward(user_id, points_to_add=points_to_change)
    
    await query.edit_message_text("✅ Perubahan berhasil disimpan!")

    # Refresh UI Admin & User (sama seperti di handle_amount_input)
    target_id = user_id
    user_data_admin = db.get_user_data(target_id)
    user_name_row = db.db_execute("SELECT u_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 1", (target_id,), fetchone=True)
    target_name = user_name_row['u_name'] if user_name_row else f"ID_{target_id}"
    text = f"👤 Mengelola Pengguna: <b>@{target_name}</b> (<code>{target_id}</code>)\n\nPilih tindakan:"
    is_banned = user_data_admin and user_data_admin.get('is_banned')
    ban_button = InlineKeyboardButton("✅ Unban User", callback_data=f"admin_confirm_unban:{target_id}") if is_banned else InlineKeyboardButton("🚫 Ban User", callback_data=f"admin_confirm_ban:{target_id}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Lihat Info Lengkap", callback_data=f"admin_info_user:{target_id}")],
        [InlineKeyboardButton("✏️ Edit Kuota & Poin", callback_data=f"admin_edit_quota_menu:{target_id}")],
        [ban_button],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar User", callback_data="admin_choose_user:info:0")]
    ])
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=keyboard, parse_mode="HTML")
    try:
        user_data_live = db.get_user_data(user_id)
        last_menu_id = user_data_live.get('last_menu_id') if user_data_live else None
        if last_menu_id:
            user_info = await context.bot.get_chat(user_id)
            username = user_info.username or user_info.full_name or "User"
            new_text, new_keyboard = utils.build_main_menu_message(user_id, username)
            await context.bot.edit_message_text(chat_id=user_id, message_id=last_menu_id, text=new_text, reply_markup=new_keyboard, parse_mode="Markdown")
    except Exception as e:
        config.logger.warning(f"Gagal me-refresh menu utama user: {e}")

    # --- BAGIAN KUNCI: Bersihkan semua data sesi ---
    for key in ['admin_edit_action', 'admin_edit_target_uid', 'admin_edit_pkg_type', 'admin_edit_amount']:
        context.chat_data.pop(key, None)

    return ConversationHandler.END

async def handle_amount_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Memproses jumlah yang dimasukkan admin, mengupdate DB, dan me-refresh semua UI."""
    try:
        amount = int(update.message.text)
        if amount < 0:
            await update.message.reply_text("⚠️ Harap masukkan angka positif.")
            return K.STATE_ADMIN_GET_EDIT_AMOUNT
    except ValueError:
        await update.message.reply_text("⚠️ Harap masukkan angka yang valid.")
        return K.STATE_ADMIN_GET_EDIT_AMOUNT

    action = context.chat_data.get('admin_edit_action')
    user_id = context.chat_data.get('admin_edit_target_uid')
    pkg_type = context.chat_data.get('admin_edit_pkg_type')
    
    if not action or not user_id:
        await update.message.reply_text("❌ Sesi tidak valid. Harap ulangi.")
        return ConversationHandler.END

    success_text = ""
    # Logika Update Database
    if action in ["add_kuota", "sub_kuota"]:
        field = f"paket_{pkg_type}_posts"; operator = "+" if action == "add_kuota" else "-"
        db.db_execute(f"UPDATE user_rewards SET {field} = MAX(0, {field} {operator} %s) WHERE u_id = %s", (amount, user_id))
        success_text = f"Kuota {pkg_type.title()} berhasil diubah."
    elif action in ["add_reward", "sub_reward"]:
        operator = "+" if action == "add_reward" else "-"
        db.db_execute(f"UPDATE user_rewards SET available_rewards = MAX(0, available_rewards {operator} %s) WHERE u_id = %s", (amount, user_id))
        success_text = f"Tiket Reward berhasil diubah."
    elif action in ["add_poin", "sub_poin"]:
        points_to_change = amount if action == "add_poin" else -amount
        db.increment_and_check_reward(user_id, points_to_add=points_to_change)
        success_text = "Poin Reward berhasil diubah."
        
    # --- Tampilkan UI Kembali ke ADMIN ---
    success_msg = await update.message.reply_text(f"✅ Berhasil!\n{success_text}")
    try: await update.message.delete()
    except: pass
    context.job_queue.run_once(utils.delete_message_after_delay, 2, chat_id=update.effective_chat.id, data={'message_id': success_msg.message_id})

    target_id = user_id
    user_data_admin = db.get_user_data(target_id)
    user_name_row = db.db_execute("SELECT u_name FROM submissions WHERE u_id = %s ORDER BY timestamp DESC LIMIT 1", (target_id,), fetchone=True)
    target_name = user_name_row['u_name'] if user_name_row else f"ID_{target_id}"
    text = f"👤 Mengelola Pengguna: <b>@{target_name}</b> (<code>{target_id}</code>)\n\nPilih tindakan:"
    is_banned = user_data_admin and user_data_admin.get('is_banned')
    ban_button = InlineKeyboardButton("✅ Unban User", callback_data=f"admin_confirm_unban:{target_id}") if is_banned else InlineKeyboardButton("🚫 Ban User", callback_data=f"admin_confirm_ban:{target_id}")
    keyboard = InlineKeyboardMarkup([
        [InlineKeyboardButton("ℹ️ Lihat Info Lengkap", callback_data=f"admin_info_user:{target_id}")],
        [InlineKeyboardButton("✏️ Edit Kuota & Poin", callback_data=f"admin_edit_quota_menu:{target_id}")],
        [ban_button],
        [InlineKeyboardButton("⬅️ Kembali ke Daftar User", callback_data="admin_choose_user:info:0")]
    ])
    if last_msg_id := context.chat_data.pop('last_bot_message_id', None):
        try: await context.bot.delete_message(update.effective_chat.id, last_msg_id)
        except: pass
    await context.bot.send_message(chat_id=update.effective_chat.id, text=text, reply_markup=keyboard, parse_mode="HTML")

    # --- BAGIAN KUNCI: REFRESH MENU UTAMA PENGGUNA ---
    try:
        user_data_live = db.get_user_data(user_id)
        last_menu_id = user_data_live.get('last_menu_id') if user_data_live else None

        if last_menu_id:
            user_info = await context.bot.get_chat(user_id)
            username = user_info.username or user_info.full_name or "User"
            
            new_text, new_keyboard = utils.build_main_menu_message(user_id, username)
            
            await context.bot.edit_message_text(
                chat_id=user_id,
                message_id=last_menu_id,
                text=new_text,
                reply_markup=new_keyboard,
                parse_mode="Markdown"
            )
            config.logger.info(f"Menu utama untuk user {user_id} berhasil di-refresh oleh admin.")
    except Exception as e:
        config.logger.warning(f"Gagal me-refresh menu utama untuk user {user_id} (mungkin pesan tidak ada): {e}")
    # --- AKHIR BAGIAN KUNCI ---

    # Bersihkan data sesi
    for key in ['admin_edit_action', 'admin_edit_target_uid', 'admin_edit_pkg_type']:
        context.chat_data.pop(key, None)

    return ConversationHandler.END

async def cancel_quota_edit(update: Update, context: ContextTypes.DEFAULT_TYPE) -> int:
    """Membatalkan alur edit kuota, kembali ke menu, dan membersihkan sesi."""
    query = update.callback_query
    await query.answer()
    
    user_id = context.chat_data.get('admin_edit_target_uid')
    
    # Jangan hapus pesan karena akan kita edit.
    
    if user_id:
        # Buat objek palsu yang benar untuk memanggil kembali menu manajemen
        fake_query = type('FakeQuery', (), {
            'data': f"admin_manage_user:{user_id}",
            'answer': utils.fake_answer_callback,
            'message': query.message,
            'from_user': query.from_user
        })()
        fake_update = type('FakeUpdate', (), {'callback_query': fake_query})()
        
        # Panggil kembali menu manajemen user
        await admin_user_management_menu(fake_update, context)
    else:
        # Fallback jika user_id tidak ditemukan
        await context.bot.send_message(query.from_user.id, "ℹ️ Aksi dibatalkan.")
    
    # Bersihkan semua data sesi
    for key in ['admin_edit_action', 'admin_edit_target_uid', 'admin_edit_pkg_type', 'admin_edit_amount']:
        context.chat_data.pop(key, None)

    return ConversationHandler.END



