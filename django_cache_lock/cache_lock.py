import logging, time, atexit
from typing import Optional
from uuid import uuid4
from functools import wraps

from django.core.cache import cache

from .settings import settings

logger = logging.getLogger(__name__)


class CacheLock:
    def __init__(
        self,
        key: str,
        timeout: Optional[float] = None,
        release_check_period: Optional[float] = None,
    ):
        """
        Initializer

        Keyword arguments:
        key: lock key
        timeout: timeout
        release_check_period: interval to check release when already locked by other lock (default: settings.RELEASE_CHECK_PERIOD)
        """
        self.uuid = str(uuid4())
        self.key = f"{settings.KEY_PREFIX}:{key}"
        self.timeout = timeout
        self.release_check_period: float = release_check_period or settings.RELEASE_CHECK_PERIOD

        def dispose():
            return cache.delete(self.key)

        self.dispose = dispose

    @property
    def is_locked(self):
        return bool(cache.get(self.key))

    @property
    def is_acquired(self):
        return bool(cache.get(self.key) == self.uuid)

    def acquire(self, block=True):
        while True:
            if self._acquire():
                logger.info(f"CacheLock ({self.uuid}) acquired lock for key '{self.key}'")
                return True
            elif not block:
                logger.info(f"CacheLock ({self.uuid}) skipped acquiring lock for key '{self.key}'")
                return False
            else:
                self._sleep()

    def release(self):
        if self.is_acquired:
            cache.delete(self.key)
            atexit.unregister(self.dispose)
            logger.info(f"CacheLock ({self.uuid}) released lock for key '{self.key}'")
        else:
            logger.error(f"CacheLock ({self.uuid}) cannot release for key '{self.key}'. It is already released")

    def force_release(self):
        cache.delete(self.key)
        logger.info(f"CacheLock ({self.uuid}) forcibly released lock for key '{self.key}'")

    def touch(self):
        logger.debug(f"CacheLock ({self.uuid}) set timeout to {self.timeout} second(s) for key '{self.key}'")
        return cache.touch(self.key, self.timeout)

    def _acquire(self):
        if self.is_acquired:
            return True
        elif cache.add(self.key, self.uuid, self.timeout) and self.is_acquired:
            atexit.register(self.dispose)
            return True
        else:
            return False

    def _sleep(self):
        while self.is_locked:
            logger.debug(
                f"Lock ({self.key}) is locked, CacheLock ({self.uuid}) will sleep for {self.release_check_period} seconds"
            )
            time.sleep(self.release_check_period)

    def __enter__(self):
        self.acquire()

    def __exit__(self, type, value, traceback):
        self.release()


def mutex(
    key: str,
    timeout: Optional[float] = None,
    release_check_period: Optional[float] = None,
    skip_if_blocked: bool = False,
    attribute_name_as_identifier: Optional[str] = None,
):
    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if attribute_name_as_identifier and args and hasattr(args[0], attribute_name_as_identifier):
                lock_key = f"{key}:{getattr(args[0], attribute_name_as_identifier)}"
            else:
                lock_key = key

            lock = CacheLock(lock_key, timeout, release_check_period)
            is_acquired = lock.acquire(block=False)
            if not is_acquired and skip_if_blocked:
                return
            with lock:
                result = func(*args, **kwargs)
            return result

        return wrapper

    return decorator
