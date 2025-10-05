import sqlite3

# --- KONFIGURASI ---
DB_LAMA_FILE = 'jastip_data1.db'
DB_BARU_FILE = 'jastip_data.db'

# --- Daftar Nama Tabel yang Mungkin (Prioritas dari kiri ke kanan) ---
KEMUNGKINAN_NAMA_USERS = ['user_rewards', 'users', 'user_data']
KEMUNGKINAN_NAMA_SUBMISSIONS = ['submissions', 'jastips', 'posts']


def get_connection(db_file):
    """Membuat koneksi yang mengembalikan baris sebagai dictionary."""
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    return con

def find_table_name(cursor, possible_names):
    """Mencari nama tabel yang valid dari daftar kemungkinan."""
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    existing_tables = [row['name'] for row in cursor.fetchall()]
    for name in possible_names:
        if name in existing_tables:
            print(f"    -> Tabel '{name}' ditemukan.")
            return name
    return None

def migrate():
    con_lama = None
    con_baru = None
    try:
        # --- Koneksi ---
        con_lama = get_connection(DB_LAMA_FILE)
        cur_lama = con_lama.cursor()
        print(f"Berhasil terhubung ke database lama '{DB_LAMA_FILE}'.")
        
        con_baru = get_connection(DB_BARU_FILE)
        cur_baru = con_baru.cursor()
        print(f"Berhasil terhubung ke database baru '{DB_BARU_FILE}'.")

        # --- Deteksi Nama Tabel Otomatis ---
        print("\n[Langkah 1] Mendeteksi nama tabel di database lama...")
        table_users_lama = find_table_name(cur_lama, KEMUNGKINAN_NAMA_USERS)
        table_submissions_lama = find_table_name(cur_lama, KEMUNGKINAN_NAMA_SUBMISSIONS)

        if not table_users_lama:
            raise Exception(f"Tidak dapat menemukan tabel pengguna. Sudah coba: {KEMUNGKINAN_NAMA_USERS}")
        if not table_submissions_lama:
            raise Exception(f"Tidak dapat menemukan tabel pengajuan. Sudah coba: {KEMUNGKINAN_NAMA_SUBMISSIONS}")

        # --- Migrasi Tabel Pengguna ---
        print(f"\n[Langkah 2] Memigrasikan data dari '{table_users_lama}' ke 'user_rewards'...")
        
        cur_lama.execute(f"SELECT * FROM {table_users_lama}")
        rows_lama = cur_lama.fetchall()
        
        data_to_insert = []
        for row in rows_lama:
            # Dapatkan daftar kunci (nama kolom) untuk baris ini
            keys = row.keys()
            
            # Bangun dictionary data baru dengan aman
            new_row_data = {
                'last_menu_id': None,
                'paket_dasar_posts': 0,
                'paket_hemat_posts': 0,
                'paket_sultan_posts': 0,
                'is_banned': row['is_banned'] if 'is_banned' in keys else 0,
                'u_id': row['u_id'] if 'u_id' in keys else row.get('user_id'),
                'submission_count': row['submission_count'] if 'submission_count' in keys else row.get('post_count', 0),
                'available_rewards': row['available_rewards'] if 'available_rewards' in keys else row.get('reward_tickets', 0)
            }
            data_to_insert.append(new_row_data)

        if data_to_insert:
            cur_baru.executemany("""
                INSERT OR IGNORE INTO user_rewards (
                    u_id, submission_count, available_rewards, is_banned, last_menu_id,
                    paket_dasar_posts, paket_hemat_posts, paket_sultan_posts
                ) VALUES (
                    :u_id, :submission_count, :available_rewards, :is_banned, :last_menu_id,
                    :paket_dasar_posts, :paket_hemat_posts, :paket_sultan_posts
                )
            """, data_to_insert)
            print(f"    -> {cur_baru.rowcount} baris diproses untuk 'user_rewards'.")
            con_baru.commit()

        # --- Migrasi Tabel Pengajuan ---
        print(f"\n[Langkah 3] Memigrasikan data dari '{table_submissions_lama}' ke 'submissions'...")

        cur_lama.execute(f"SELECT * FROM {table_submissions_lama}")
        rows_lama = cur_lama.fetchall()

        data_to_insert = []
        for row in rows_lama:
            keys = row.keys()
            new_row_data = {
                'unique_id': row['unique_id'],
                'timestamp': row['timestamp'],
                'photo_file_id': row['photo_file_id'],
                'user_confirmation_msg_id': None, # Selalu reset
                'u_id': row['u_id'] if 'u_id' in keys else row['user_id'],
                'u_name': row['u_name'] if 'u_name' in keys else row.get('username'),
                'pet_name': row['pet_name'] if 'pet_name' in keys else row.get('description'),
                'user_tele': row['user_tele'] if 'user_tele' in keys else row.get('contact'),
                'status': row['status'] if 'status' in keys else 'pending',
                'post_link': row['post_link'] if 'post_link' in keys else None,
                'submission_msg_id': row['submission_msg_id'] if 'submission_msg_id' in keys else None,
                'is_reward': row['is_reward'] if 'is_reward' in keys else 0,
                'payment_status': row['payment_status'] if 'payment_status' in keys else 'unpaid'
            }
            data_to_insert.append(new_row_data)
            
        if data_to_insert:
            cur_baru.executemany("""
                INSERT OR IGNORE INTO submissions (
                    unique_id, timestamp, u_id, u_name, pet_name, user_tele, 
                    photo_file_id, status, post_link, submission_msg_id, 
                    is_reward, payment_status, user_confirmation_msg_id
                ) VALUES (
                    :unique_id, :timestamp, :u_id, :u_name, :pet_name, :user_tele, 
                    :photo_file_id, :status, :post_link, :submission_msg_id, 
                    :is_reward, :payment_status, :user_confirmation_msg_id
                )
            """, data_to_insert)
            print(f"    -> {cur_baru.rowcount} baris diproses untuk 'submissions'.")
            con_baru.commit()

        print("\n[SELESAI] Migrasi berhasil!")

    except Exception as e:
        print(f"\n[ERROR] Terjadi error fatal saat migrasi: {e}")
        if con_baru: con_baru.rollback()
        print("    -> Perubahan di database baru telah dibatalkan (rollback).")
    finally:
        if con_lama: con_lama.close()
        if con_baru: con_baru.close()
        print("Koneksi ke database ditutup.")

if __name__ == "__main__":
    migrate()