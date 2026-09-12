"""Optional local access-key exchange; browser sessions are never static keys.

Single-process, single-user scope. Restart and configured-key rotation invalidate
all sessions. The OS account and loopback checks remain mandatory boundaries.
"""
import hashlib
import secrets
import threading
import time


class AccessSessions:
    IDLE_SECONDS = 15 * 60
    MAX_SECONDS = 8 * 60 * 60
    ATTEMPTS = 5
    WINDOW_SECONDS = 60
    MAX_SESSIONS = 16

    def __init__(self, clock=time.monotonic):
        self.clock = clock
        self.lock = threading.Lock()
        self.sessions = {}
        self.failures = []
        self.key_digest = None

    def _sync(self, key):
        digest = hashlib.sha256(key.encode()).digest()
        if digest != self.key_digest:
            self.sessions.clear()
            self.failures.clear()
            self.key_digest = digest
        now = self.clock()
        self.failures = [t for t in self.failures if now - t < self.WINDOW_SECONDS]
        self.sessions = {k: v for k, v in self.sessions.items()
                         if now - v[0] < self.MAX_SECONDS and now - v[1] < self.IDLE_SECONDS}
        return now

    def issue(self, key, supplied, previous=''):
        with self.lock:
            now = self._sync(key)
            if len(self.failures) >= self.ATTEMPTS:
                return None, max(1, int(self.WINDOW_SECONDS - (now - self.failures[0])) + 1)
            if not key or not secrets.compare_digest(supplied.encode(), key.encode()):
                self.failures.append(now)
                return None, 0
            self.sessions.pop(self._digest(previous), None)
            if len(self.sessions) >= self.MAX_SESSIONS:
                oldest = min(self.sessions, key=lambda k: self.sessions[k][1])
                del self.sessions[oldest]
            token = secrets.token_urlsafe(32)
            self.sessions[self._digest(token)] = (now, now)
            return token, 0

    @staticmethod
    def _digest(token):
        return hashlib.sha256(token.encode()).digest()

    def verify(self, key, token):
        with self.lock:
            now = self._sync(key)
            digest = self._digest(token)
            session = self.sessions.get(digest)
            if not key or not token or session is None:
                return False
            self.sessions[digest] = (session[0], now)
            return True

    def revoke(self, token):
        with self.lock:
            self.sessions.pop(self._digest(token), None)


sessions = AccessSessions()
