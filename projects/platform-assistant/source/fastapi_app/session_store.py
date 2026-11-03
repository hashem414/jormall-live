import threading
import time
import uuid


MAX_HISTORY_TURNS = 6


class SessionStore:
    def __init__(self, max_age_seconds):
        self._state_lock = threading.Lock()
        self._locks = {}
        self._histories = {}
        self._last_seen = {}
        self._max_age_seconds = max_age_seconds

    def new_session_id(self):
        return str(uuid.uuid4())

    def get_lock(self, session_id):
        with self._state_lock:
            self._last_seen[session_id] = time.time()
            if session_id not in self._locks:
                self._locks[session_id] = threading.Lock()
            return self._locks[session_id]

    def get_history(self, session_id):
        with self._state_lock:
            self._last_seen[session_id] = time.time()
            return list(self._histories.get(session_id, []))

    def append_history(self, session_id, query, answer):
        with self._state_lock:
            self._last_seen[session_id] = time.time()
            history = self._histories.setdefault(session_id, [])
            history.append((query, answer))
            if len(history) > MAX_HISTORY_TURNS:
                del history[:-MAX_HISTORY_TURNS]

    def touch(self, session_id):
        with self._state_lock:
            self._last_seen[session_id] = time.time()

    def cleanup_expired(self):
        cutoff = time.time() - self._max_age_seconds
        with self._state_lock:
            expired = [
                session_id
                for session_id, last_seen in self._last_seen.items()
                if last_seen < cutoff
            ]
            for session_id in expired:
                self._last_seen.pop(session_id, None)
                self._histories.pop(session_id, None)
                self._locks.pop(session_id, None)
            return len(expired)

    def session_count(self):
        with self._state_lock:
            return len(self._locks)
