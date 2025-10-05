# File: database.py (Versi Supabase/PostgreSQL)

import psycopg2
import psycopg2.extras # Ini penting agar hasil query bisa seperti dictionary
import config

def get_db_connection():
    """Membuat koneksi ke database PostgreSQL di Supabase."""
    # Koneksi sekarang menggunakan DATABASE_URL dari config, bukan nama file
    con = psycopg2.connect(config.DATABASE_URL)
    return con

def init_db():
    """
    Memastikan semua tabel yang dibutuhkan ada di database Supabase.
    Bisa dijalankan sekali saat setup awal.
    """
    # Di PostgreSQL, tipe data untuk ID auto-increment adalah SERIAL PRIMARY KEY
    # dan BIGINT lebih aman untuk ID Telegram yang bisa sangat besar.
    create_statements = [
        """
        CREATE TABLE IF NOT EXISTS submissions (
            unique_id TEXT PRIMARY KEY, timestamp TEXT NOT NULL, u_id BIGINT NOT NULL,
            u_name TEXT, pet_name TEXT, user_tele TEXT, photo_file_id TEXT,
            status TEXT DEFAULT 'pending', post_link TEXT, submission_msg_id BIGINT,
            is_reward INTEGER DEFAULT 0, payment_status TEXT DEFAULT 'unpaid',
            user_confirmation_msg_id BIGINT, bot_qris_msg_id BIGINT,
            user_proof_msg_id BIGINT, user_notice_msg_id BIGINT
        );""",
        """
        CREATE TABLE IF NOT EXISTS user_rewards (
            u_id BIGINT PRIMARY KEY, submission_count INTEGER DEFAULT 0,
            available_rewards INTEGER DEFAULT 0, is_banned INTEGER DEFAULT 0,
            last_menu_id BIGINT, paket_dasar_posts INTEGER DEFAULT 0,
            paket_hemat_posts INTEGER DEFAULT 0, paket_sultan_posts INTEGER DEFAULT 0,
            pending_qris_msg_id BIGINT, pending_proof_msg_id BIGINT
        );""",
        """
        CREATE TABLE IF NOT EXISTS bot_settings (key TEXT PRIMARY KEY, value TEXT);""",
        # Di PostgreSQL, 'INSERT OR IGNORE' ditulis 'INSERT ... ON CONFLICT ... DO NOTHING'
        "INSERT INTO bot_settings (key, value) VALUES ('maintenance_mode', 'off') ON CONFLICT (key) DO NOTHING;"
    ]

    with get_db_connection() as con:
        with con.cursor() as cur:
            for statement in create_statements:
                cur.execute(statement)
        con.commit()
    config.logger.info("Database tables successfully ensured in Supabase.")

def db_execute(query, params=(), fetchone=False, fetchall=False):
    """Fungsi generik untuk eksekusi query. PENTING: Menggunakan %s, bukan ?"""
    with get_db_connection() as con:
        # DictCursor membuat hasil query bisa diakses seperti: row['nama_kolom']
        # Ini membuat kodenya kompatibel dengan kode lamamu yang pakai sqlite3.Row
        with con.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # PERHATIAN: Parameter di psycopg2 menggunakan placeholder '%s', BUKAN '?'
            cur.execute(query, params)
            
            result = None
            if fetchone:
                result = cur.fetchone()
            if fetchall:
                result = cur.fetchall()
            
            # Commit (simpan perubahan) hanya jika query bukan SELECT
            if not query.strip().upper().startswith("SELECT"):
                con.commit()
            return result

# --- Di bawah ini adalah SEMUA FUNGSI LAMAMU, HANYA DIUBAH PLACEHOLDER-NYA ---

def get_user_data(user_id: int):
    data = db_execute("SELECT * FROM user_rewards WHERE u_id = %s", (user_id,), fetchone=True)
    return dict(data) if data else None

def has_any_kuota(user_id: int) -> bool:
    data = get_user_data(user_id)
    if not data: return False
    return any([data['available_rewards'] > 0, data['paket_dasar_posts'] > 0, data['paket_hemat_posts'] > 0, data['paket_sultan_posts'] > 0])

def is_user_banned(user_id: int) -> bool:
    result = db_execute("SELECT is_banned FROM user_rewards WHERE u_id = %s", (user_id,), fetchone=True)
    return result and result['is_banned'] == 1

def add_submission(data: dict):
    # Kita pakai placeholder bernama (%(key)s) agar lebih jelas dan aman
    query = """
        INSERT INTO submissions (
            unique_id, timestamp, u_id, u_name, pet_name, user_tele, 
            photo_file_id, status, post_link, submission_msg_id, 
            is_reward, payment_status, user_confirmation_msg_id
        ) VALUES (
            %(unique_id)s, %(timestamp)s, %(u_id)s, %(u_name)s, %(pet_name)s, %(user_tele)s, 
            %(photo_file_id)s, %(status)s, %(post_link)s, %(submission_msg_id)s, 
            %(is_reward)s, %(payment_status)s, %(user_confirmation_msg_id)s
        ) ON CONFLICT (unique_id) DO NOTHING;
    """
    db_execute(query, data)

def update_submission(unique_id: str, updates: dict):
    fields = ", ".join([f"{key} = %s" for key in updates.keys()])
    params = list(updates.values()) + [unique_id]
    db_execute(f"UPDATE submissions SET {fields} WHERE unique_id = %s", params)

def get_submission_by_id(unique_id: str):
    data = db_execute("SELECT * FROM submissions WHERE unique_id = %s", (unique_id,), fetchone=True)
    return dict(data) if data else None

def get_submissions_by_user(u_id: int):
    return db_execute("SELECT * FROM submissions WHERE u_id = %s AND status = 'on sale' ORDER BY timestamp DESC", (u_id,), fetchall=True)

def get_last_pending_submission_by_user(u_id: int):
    data = db_execute("SELECT * FROM submissions WHERE u_id = %s AND status = 'pending' AND payment_status = 'unpaid' ORDER BY timestamp DESC LIMIT 1", (u_id,), fetchone=True)
    return dict(data) if data else None
    
def increment_and_check_reward(u_id: int, points_to_add: int = 1):
    # INSERT ... ON CONFLICT (u_id) DO NOTHING; adalah cara PostgreSQL untuk 'INSERT OR IGNORE'
    db_execute("INSERT INTO user_rewards (u_id) VALUES (%s) ON CONFLICT (u_id) DO NOTHING;", (u_id,))
    
    current_points_row = db_execute("SELECT submission_count FROM user_rewards WHERE u_id = %s", (u_id,), fetchone=True)
    current_points = current_points_row['submission_count'] if current_points_row else 0
    new_points = max(0, current_points + points_to_add)
    rewards_earned = new_points // 5
    remaining_points = new_points % 5
    
    if rewards_earned > 0:
        db_execute("UPDATE user_rewards SET available_rewards = available_rewards + %s, submission_count = %s WHERE u_id = %s", (rewards_earned, remaining_points, u_id))
        config.logger.info(f"User {u_id} MENDAPATKAN +{rewards_earned} reward. Poin direset menjadi {remaining_points}.")
        return True
    else:
        db_execute("UPDATE user_rewards SET submission_count = %s WHERE u_id = %s", (new_points, u_id))
        return False

def get_setting(key: str, default: str = None) -> str:
    result = db_execute("SELECT value FROM bot_settings WHERE key = %s", (key,), fetchone=True)
    return result['value'] if result else default

def set_setting(key: str, value: str):
    # INSERT ... ON CONFLICT (key) DO UPDATE ... adalah cara PostgreSQL untuk 'INSERT OR REPLACE'
    db_execute("INSERT INTO bot_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value;", (key, value))

def count_user_submissions_by_status(user_id: int, status: str) -> int:
    query = "SELECT COUNT(*) FROM submissions WHERE u_id = %s AND status = %s"
    result = db_execute(query, (user_id, status), fetchone=True)
    return result[0] if result else 0


if __name__ == "__main__":
    init_db()