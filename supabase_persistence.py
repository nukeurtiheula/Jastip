# File baru: supabase_persistence.py (Versi Lengkap dan Benar)

import json
from telegram.ext import BasePersistence
from typing import Dict, Any, Optional, Tuple, cast

import database as db
import config

class SupabasePersistence(BasePersistence):
    """
    Persistence class that uses Supabase (PostgreSQL) as a backend.
    """
    def __init__(self):
        super().__init__(store_user_data=True, store_chat_data=True, store_bot_data=True)

    # --- FUNGSI INTI UNTUK KOMUNIKASI DB ---

    def _get_data_from_db(self, type: str, id: int) -> Optional[Dict]:
        """Fetches data from the ptb_persistence table."""
        try:
            query = "SELECT data FROM ptb_persistence WHERE type = %s AND id = %s"
            result = db.db_execute(query, (type, id), fetchone=True)
            return json.loads(result['data']) if result and result['data'] else {}
        except Exception as e:
            config.logger.error(f"Error getting {type} data for ID {id} from DB: {e}")
            return {}

    def _update_data_in_db(self, type: str, id: int, data: Dict) -> None:
        """Updates or inserts data into the ptb_persistence table."""
        try:
            query = """
                INSERT INTO ptb_persistence (type, id, data)
                VALUES (%s, %s, %s)
                ON CONFLICT (type, id) DO UPDATE SET data = EXCLUDED.data;
            """
            db.db_execute(query, (type, id, json.dumps(data)))
        except Exception as e:
            config.logger.error(f"Error updating {type} data for ID {id} in DB: {e}")

    # --- IMPLEMENTASI METODE WAJIB (ABSTRAK) ---

    async def get_bot_data(self) -> Dict[Any, Any]:
        return self._get_data_from_db('bot', 0)

    async def update_bot_data(self, data: Dict[Any, Any]) -> None:
        self._update_data_in_db('bot', 0, data)

    async def get_chat_data(self) -> Dict[int, Dict[Any, Any]]:
        # Di serverless, kita tidak memuat semua chat data sekaligus. Ini hanya placeholder.
        return {}

    async def update_chat_data(self, chat_id: int, data: Dict[Any, Any]) -> None:
        self._update_data_in_db('chat', chat_id, data)

    async def get_user_data(self) -> Dict[int, Dict[Any, Any]]:
        # Di serverless, kita tidak memuat semua user data sekaligus. Ini hanya placeholder.
        return {}

    async def update_user_data(self, user_id: int, data: Dict[Any, Any]) -> None:
        self._update_data_in_db('user', user_id, data)

    async def get_conversations(self, name: str) -> Dict[Tuple, Any]:
        conv_data = self._get_data_from_db(f"conv_{name}", 0)
        # Kunci di JSON adalah string, kita perlu mengubahnya kembali menjadi tuple
        return {eval(key): value for key, value in conv_data.items()}

    async def update_conversation(self, name: str, key: Tuple, new_state: Optional[object]) -> None:
        convs = await self.get_conversations(name)
        # Kunci tuple harus diubah menjadi string untuk disimpan di JSON
        str_key = str(key)
        if new_state is None:
            convs.pop(str_key, None)
        else:
            convs[str_key] = new_state
        self._update_data_in_db(f"conv_{name}", 0, convs)

    async def get_callback_data(self) -> Optional[Any]:
        # Callback data tidak di-persist di Vercel
        return None

    async def update_callback_data(self, data: Any) -> None:
        # Callback data tidak di-persist di Vercel
        pass
        
    async def drop_chat_data(self, chat_id: int) -> None:
        db.db_execute("DELETE FROM ptb_persistence WHERE type = 'chat' AND id = %s", (chat_id,))

    async def drop_user_data(self, user_id: int) -> None:
        db.db_execute("DELETE FROM ptb_persistence WHERE type = 'user' AND id = %s", (user_id,))
        
    async def refresh_bot_data(self, bot_data: Dict) -> None:
        data = await self.get_bot_data()
        bot_data.clear()
        bot_data.update(data)

    async def refresh_chat_data(self, chat_id: int, chat_data: Dict) -> None:
        data = self._get_data_from_db("chat", chat_id)
        chat_data.clear()
        chat_data.update(data)

    async def refresh_user_data(self, user_id: int, user_data: Dict) -> None:
        data = self._get_data_from_db("user", user_id)
        user_data.clear()
        user_data.update(data)

    async def flush(self) -> None:
        # Tidak perlu, karena kita menyimpan langsung ke DB
        pass

# tes