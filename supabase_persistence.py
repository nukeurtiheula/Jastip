# File baru: supabase_persistence.py

import json
from telegram.ext import BasePersistence
from typing import Dict, Any, Optional

import database as db

class SupabasePersistence(BasePersistence):
    def __init__(self):
        super().__init__(store_user_data=True, store_chat_data=True, store_bot_data=True)

    def _get_data(self, type: str, id: int) -> Optional[Dict]:
        query = "SELECT data FROM ptb_persistence WHERE type = %s AND id = %s"
        result = db.db_execute(query, (type, id), fetchone=True)
        return result['data'] if result and result['data'] else {}

    def _update_data(self, type: str, id: int, data: Dict) -> None:
        # Menggunakan JSONB di PostgreSQL sangat efisien
        query = """
            INSERT INTO ptb_persistence (type, id, data)
            VALUES (%s, %s, %s)
            ON CONFLICT (type, id) DO UPDATE SET data = EXCLUDED.data;
        """
        db.db_execute(query, (type, id, json.dumps(data)))

    def get_user_data(self) -> Dict[int, Dict[Any, Any]]:
        # Fungsi ini sebenarnya tidak perlu diimplementasikan secara penuh di serverless
        # karena data diambil per-user saat dibutuhkan.
        return self.user_data

    def get_chat_data(self) -> Dict[int, Dict[Any, Any]]:
        return self.chat_data

    def get_bot_data(self) -> Dict[str, Any]:
        return self.bot_data

    def update_user_data(self, user_id: int, data: Dict) -> None:
        self._update_data('user', user_id, data)

    def update_chat_data(self, chat_id: int, data: Dict) -> None:
        self._update_data('chat', chat_id, data)

    def update_bot_data(self, data: Dict) -> None:
        # Kita gunakan ID 0 untuk bot_data
        self._update_data('bot', 0, data)
        
    async def get_conversations(self, name: str) -> dict:
        result = db.db_execute("SELECT data FROM ptb_persistence WHERE type = %s AND id = %s", (f"conv_{name}", 0), fetchone=True)
        return json.loads(result['data']) if result and result['data'] else {}

    async def update_conversation(self, name: str, key: tuple, new_state: object) -> None:
        convs = await self.get_conversations(name)
        if new_state is None:
            convs.pop(key, None)
        else:
            convs[key] = new_state
            
        query = """
            INSERT INTO ptb_persistence (type, id, data)
            VALUES (%s, %s, %s)
            ON CONFLICT (type, id) DO UPDATE SET data = EXCLUDED.data;
        """
        db.db_execute(query, (f"conv_{name}", 0, json.dumps(convs)))

    async def flush(self) -> None:
        # Tidak perlu melakukan apa-apa karena kita menyimpan data secara langsung
        pass