from django.core.cache import cache

from .settings import settings


class CacheLock:
    def __init__(self, id: str, timeout: int | None = None) -> None:
        self.id = id
        self._cache_timeout = timeout

    @property
    def id(self) -> str:
        return self._id

    @id.setter
    def id(self, id: str) -> None:
        self._id = id
        self._cache_key = f"{settings.CACHE_KEY_PREFIX}:{id}"

    @property
    def lock_key(self) -> str | None:
        return cache.get(self._cache_key)

    def is_locked(self) -> bool:
        return bool(self.lock_key)

    def is_locked_by(self, lock_key) -> bool:
        return self.lock_key == lock_key

    def lock_with(self, lock_key: str) -> bool:
        cache.add(self._cache_key, lock_key, self._cache_timeout)
        return self.is_locked_by(lock_key)

    def unlock_with(self, lock_key: str) -> bool:
        if not self.is_locked():
            return True
        if not self.is_locked_by(lock_key):
            return False
        else:
            return self.unlock()

    def unlock(self) -> bool:
        if not self.is_locked():
            return True
        else:
            return cache.delete(self._cache_key)

    def touch(self, timeout: int | None = None) -> bool:
        return cache.touch(self._cache_key, timeout or self._cache_timeout)

    def __repr__(self) -> str:
        return f"CacheLock(id={self.id}, timeout={self._cache_timeout})"

    def __str__(self) -> str:
        return f"CacheLock({self.id})"
