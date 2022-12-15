import logging, time
from uuid import uuid4
from functools import wraps

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
        logger.info(f"Attempting to acquire lock for key '{self.key}'")
        while not self._try_blocking():
            if self.is_acquired or not block:
                break
            self.sleep()
        return self.is_acquired

    def release(self):
        logger.info(f"Releasing lock for key '{self.key}'")
        if self.is_acquired:
            cache.delete(self.key)

    def _try_blocking(self):
        return cache.add(self.key, self.uuid, None)

    def sleep(self):
        while self.is_locked:
            logger.debug(f"Lock is locked, sleeping for {self.release_check_period} seconds")
            time.sleep(self.release_check_period)

    def __del__(self):
        self.release()

    def __enter__(self):
        self.acquire()

    def __exit__(self, type, value, traceback):
        self.release()


def mutex(key, skip_if_blocked=False):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            lock = CacheLock(key)
            is_acquired = lock.acquire(block=False)
            if not is_acquired and skip_if_blocked:
                return
            with lock:
                result = func(*args, **kwargs)
            return result

        return wrapper

    return decorator
