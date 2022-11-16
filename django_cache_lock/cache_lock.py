import logging, time
from uuid import uuid4

from django.core.cache import cache

from .settings import settings

logger = logging.getLogger(__name__)


class CacheLock:
    def __init__(self, key, release_check_period=None):
        self.key = f"{settings.KEY_PREFIX}:{key}"
        self.release_check_period: float = release_check_period or settings.RELEASE_CHECK_PERIOD
        self.uuid = str(uuid4())

    @property
    def is_locked(self):
        return bool(cache.get(self.key))

    @property
    def is_acquired(self):
        return bool(cache.get(self.key) == self.uuid)

    def acquire(self, block=True):
        while not self._try_blocking():
            if self.is_acquired or not block:
                break
            self.sleep()
        return self.is_acquired

    def release(self):
        if self.is_acquired:
            cache.delete(self.key)

    def _try_blocking(self):
        return cache.add(self.key, self.uuid, None)

    def sleep(self):
        while self.is_locked:
            time.sleep(self.release_check_period)

    def __del__(self):
        self.release()

    def __enter__(self):
        self.acquire()

    def __exit__(self, type, value, traceback):
        self.release()
