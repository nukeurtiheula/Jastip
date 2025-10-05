# File: api/index.py (Versi FINAL BOSS - Perbaikan NameError)

import asyncio
from flask import Flask, request
from telegram import Update
from telegram.ext import (
    Application, CommandHandler, MessageHandler, CallbackQueryHandler,
    ConversationHandler, filters
)

# --- 1. Import semua file-mu ---
import config
import database as db
import constants as K
from handlers import user_conversation as usr_conv, user_callbacks as usr_cb
from handlers import admin_conversation as adm_conv, admin_callbacks as adm_cb

# ==============================================================================
# ### BAGIAN YANG DIPERBAIKI ADA DI SINI ###
# Kita definisikan SEMUANYA di luar fungsi agar bisa diakses secara global
# ==============================================================================

# --- 2. Inisialisasi Bot ---
# Kita beri nama 'application' agar tidak bentrok dengan Flask 'app'
application = Application.builder().token(config.TOKEN).build()
db.init_db()

# --- 3. Definisi ConversationHandler ---
# (Ini adalah blok kode ConversationHandler-mu yang LENGKAP)
user_submission_conv = ConversationHandler(
    entry_points=[
    CallbackQueryHandler(usr_conv.mulai_submit_callback, pattern="^mulai_submit$"),
    CallbackQueryHandler(usr_conv.user_edit_callback, pattern=r"^edit:"),
    ],
    states={
    K.STATE_PHOTO: [MessageHandler(filters.PHOTO & ~filters.COMMAND, usr_conv.photo_handler)],
    K.STATE_PET_FORMAT: [MessageHandler(filters.TEXT & ~filters.COMMAND, usr_conv.pet_format_handler), CallbackQueryHandler(usr_conv.back_to_photo_step, pattern="^edit_photo_step$")],
    K.STATE_USER_TELE: [MessageHandler(filters.TEXT & ~filters.COMMAND, usr_conv.user_tele_handler), CallbackQueryHandler(usr_conv.back_to_desc_step, pattern="^edit_desc_step$")],
    K.STATE_FINAL_CONFIRM: [
        CallbackQueryHandler(usr_conv.confirm_final_continue_callback, pattern="^confirm_final_continue$"),
        CallbackQueryHandler(usr_conv.confirm_final_edit_callback, pattern="^confirm_final_edit$"),
        CallbackQueryHandler(usr_conv.cancel, pattern="^confirm_final_cancel$"),
        CallbackQueryHandler(usr_conv.edit_final_choice_callback, pattern=r"^edit_final_"),
        ],
    K.STATE_EDIT_PHOTO_CONFIRM: [MessageHandler(filters.PHOTO & ~filters.COMMAND, usr_conv.edit_photo_handler)],
    K.STATE_EDIT_DESC_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, usr_conv.edit_desc_handler_from_confirm)],
    K.STATE_EDIT_USER_CONFIRM: [MessageHandler(filters.TEXT & ~filters.COMMAND, usr_conv.edit_user_handler_from_confirm)],
    K.STATE_WAITING_PAYMENT: [MessageHandler(filters.PHOTO & ~filters.COMMAND, usr_conv.payment_handler)],
    K.STATE_EDIT_CHOICE: [
        CallbackQueryHandler(usr_conv.edit_choice_desc_callback, pattern="^edit_choice_desc$"),
        CallbackQueryHandler(usr_conv.edit_choice_user_callback, pattern="^edit_choice_user$"),
        CallbackQueryHandler(usr_conv.edit_choice_cancel_callback, pattern="^edit_choice_cancel$"),
        ],
    K.STATE_EDIT_DESC: [CommandHandler("cancel", usr_conv.cancel_riwayat_edit), MessageHandler(filters.TEXT & ~filters.COMMAND, usr_conv.edit_desc_handler)],
    K.STATE_EDIT_USER: [CommandHandler("cancel", usr_conv.cancel_riwayat_edit), MessageHandler(filters.TEXT & ~filters.COMMAND, usr_conv.edit_user_handler)],
    },
    fallbacks=[
        CommandHandler("cancel", usr_conv.cancel),
        CallbackQueryHandler(usr_conv.cancel_submission_callback, pattern="^cancel_submission$"),
    ],
    per_message=False,
    )

 # Alur pembelian paket oleh pengguna
user_package_conv = ConversationHandler(
    entry_points=[CallbackQueryHandler(usr_conv.proceed_to_payment_callback, pattern=r"^proceed_payment:")],
    states={K.STATE_WAITING_PACKAGE_PAYMENT: [MessageHandler(filters.PHOTO, usr_conv.package_payment_handler)]},
    fallbacks=[CommandHandler("cancel", usr_conv.cancel)],
    per_message=False,
    name="user_package_conversation",
)
    
    # Semua alur percakapan admin digabung jadi satu untuk kerapian
admin_conv = ConversationHandler(
    entry_points=[
    CallbackQueryHandler(adm_cb.admin_prompt_for_edit, pattern=r"^admin_edit_(desc|tele)$"),
    CallbackQueryHandler(adm_conv.ask_for_package_type, pattern=r"^edit_start:(add_kuota|sub_kuota):"),
    CallbackQueryHandler(adm_conv.ask_for_amount, pattern=r"^edit_start:(add_reward|sub_reward|add_poin|sub_poin):"),
    CallbackQueryHandler(adm_conv.admin_broadcast_start, pattern="^admin_broadcast_start$"),
    CallbackQueryHandler(adm_conv.admin_search_user_start, pattern="^admin_search_user_start$")
        ],
    states={
    # State untuk edit pengajuan
    K.STATE_ADMIN_EDIT_DESC_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_conv.admin_get_new_desc)],
    K.STATE_ADMIN_EDIT_TELE_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_conv.admin_get_new_tele)],
    # State untuk edit kuota
    K.STATE_ADMIN_CHOOSE_PKG_TYPE: [CallbackQueryHandler(adm_conv.ask_for_amount, pattern=r"^edit_pkg:"), CallbackQueryHandler(adm_conv.cancel_quota_edit, pattern="^admin_edit_cancel$")],
    K.STATE_ADMIN_GET_EDIT_AMOUNT: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_conv.ask_for_confirmation)],
    K.STATE_ADMIN_CONFIRM_EDIT: [CallbackQueryHandler(adm_conv.execute_amount_edit, pattern="^confirm_edit_yes$"), CallbackQueryHandler(adm_conv.cancel_quota_edit, pattern="^admin_edit_cancel$")],
    # State untuk broadcast & search
    K.STATE_ADMIN_GET_BROADCAST_MSG: [MessageHandler(filters.ALL & ~filters.COMMAND, adm_conv.admin_broadcast_get_message)],
    K.STATE_ADMIN_SEARCH_USER_INPUT: [MessageHandler(filters.TEXT & ~filters.COMMAND, adm_conv.admin_search_user_handler)],
    },
    fallbacks=[CommandHandler("cancel", adm_conv.admin_cancel)],
    per_message=False,
    name="admin_main_conversation",
)


    # --- PENDAFTARAN HANDLER DENGAN URUTAN YANG BENAR DAN BERSIH ---
    
    # GRUP 0: Perintah utama yang harus selalu aktif
app.add_handler(CommandHandler("start", usr_conv.start))
app.add_handler(CommandHandler("admin", adm_cb.admin_panel, filters=filters.ChatType.PRIVATE))

    # GRUP 1: Semua ConversationHandler (PENTING: didaftarkan sebelum handler individual)
app.add_handler(user_submission_conv)
app.add_handler(user_package_conv)
app.add_handler(admin_conv)

    # GRUP 2: Semua CallbackQueryHandler ADMIN yang individual (di luar percakapan)
app.add_handler(CallbackQueryHandler(adm_cb.admin_panel, pattern="^admin_back_main$"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_menu_user, pattern="^admin_menu_user$"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_stats, pattern="^admin_stats$"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_menu_ban_unban, pattern="^admin_menu_ban_unban$"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_choose_user_list, pattern=r"^admin_choose_user:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_user_management_menu, pattern=r"^admin_manage_user:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_info_user, pattern=r"^admin_info_user:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_edit_quota_menu, pattern=r"^admin_edit_quota_menu:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_choose_action_menu, pattern=r"^edit_type:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_confirm_action_callback, pattern=r"^admin_confirm_"))
app.add_handler(CallbackQueryHandler(adm_conv.admin_broadcast_confirm, pattern="^admin_broadcast_confirm$"))
app.add_handler(CallbackQueryHandler(adm_conv.admin_broadcast_cancel, pattern="^admin_broadcast_cancel$"))
app.add_handler(CallbackQueryHandler(adm_cb.confirm_payment_callback, pattern=r"^confirm_payment:"))
app.add_handler(CallbackQueryHandler(adm_cb.confirm_package_callback, pattern=r"^confirm_package:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_menu_submission_management, pattern="^admin_menu_submission$"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_menu_settings, pattern="^admin_menu_settings$"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_list_pending_submissions, pattern=r"^list_pending:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_view_pending_submission_detail, pattern=r"^view_pending:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_reject_submission, pattern=r"^reject_submission:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_list_editable_submissions, pattern=r"^list_editable:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_view_editable_submission_detail, pattern=r"^view_editable:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_list_active_posts, pattern=r"^list_active:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_confirm_delete_post, pattern=r"^confirm_delete:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_execute_delete_post, pattern=r"^execute_delete:"))
app.add_handler(CallbackQueryHandler(adm_cb.admin_toggle_maintenance_mode, pattern="^toggle_maintenance$"))
app.add_handler(CallbackQueryHandler(adm_cb.post_submission_callback, pattern=r"^post:")) # Cukup satu kali, yang ini untuk posting.

    # GRUP 3: Semua CallbackQueryHandler USER yang individual (di luar percakapan)
app.add_handler(CallbackQueryHandler(usr_cb.back_to_main_menu_callback, pattern="^back_to_main_menu$"))
app.add_handler(CallbackQueryHandler(usr_conv.view_packages_callback, pattern="^view_packages$"))
app.add_handler(CallbackQueryHandler(usr_conv.buy_package_callback, pattern=r"^buy_package:"))
app.add_handler(CallbackQueryHandler(usr_cb.lihat_riwayat_callback, pattern=r"^lihat_riwayat:"))
app.add_handler(CallbackQueryHandler(usr_cb.user_mark_sold_callback, pattern=r"^sold:"))

    # GRUP 4: Handler "PENANGKAP SEMUA" (HARUS DAN WAJIB PALING AKHIR)
    # Handler ini akan menangani semua tombol yang tidak cocok dengan handler di atasnya.
app.add_handler(CallbackQueryHandler(usr_cb.handle_unknown_callback, pattern=r"."))

app = Flask(__name__)

@app.route('/', methods=['POST'])
def webhook() -> str:
    try:
        update_data = request.get_json()
        update = Update.de_json(update_data, application.bot)
        asyncio.run(application.process_update(update))
        return "ok"
    except Exception as e:
        config.logger.error(f"Error processing webhook: {e}", exc_info=True)
        return "error"

@app.route('/')
def index():
    return 'Bot Jastip Aktif!'