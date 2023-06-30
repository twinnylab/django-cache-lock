import time
import uuid
import asyncio
import logging
import functools
from typing import TYPE_CHECKING

from .settings import settings
from .cache_lock import CacheLock

if TYPE_CHECKING:
    from typing import Callable

logger = logging.getLogger(__name__)


class CacheLockManager:
    def __init__(self, cache_lock: CacheLock, block: bool = True, release_check_period: float | None = None) -> None:
        self.cache_lock = cache_lock
        self.lock_key = str(uuid.uuid4())
        self.block = block
        self.release_check_period: float = release_check_period or settings.RELEASE_CHECK_PERIOD

    @property
    def state(self) -> dict:
        return {
            "cache_lock_id": self.cache_lock.id,
            "cache_lock_current_lock_key": self.cache_lock.lock_key,
            "cache_lock_manager_lock_key": self.lock_key,
            "cache_lock_manager_block": self.block,
        }

    def is_acquired(self) -> bool:
        return self.cache_lock.is_locked_by(self.lock_key)

    def acquire(self, block: bool | None = None) -> bool:
        while True:
            if self.cache_lock.lock_with(self.lock_key):
                logger.info("CacheLock acquisition successful.", extra={"data": self.state})
                return True
            elif not (block or self.block):
                logger.info("CacheLock acquisition skipped.", extra={"data": self.state})
                return False
            else:
                logger.info("Waiting to acquire CacheLock.", extra={"data": self.state})
                self._sleep_until_unlock()
                logger.info("Waiting interrupted; retrying to acquire CacheLock.", extra={"data": self.state})

    def release(self) -> bool:
        if not self.cache_lock.is_locked():
            logger.error("CacheLock release failed.", extra={"data": self.state})
            return False
        elif self.cache_lock.unlock_with(self.lock_key):
            logger.info("CacheLock release successful.", extra={"data": self.state})
            return True
        else:
            logger.error("CacheLock release failed.", extra={"data": self.state})
            return False

    def _sleep_until_unlock(self) -> None:
        while self.cache_lock.is_locked():
            time.sleep(self.release_check_period)

    def __enter__(self) -> "CacheLockManager":
        self.acquire()
        return self

    def __exit__(self, exc_type: type[Exception] | None, *exc_info) -> bool:
        if exc_type == CacheLockManager.AlreadyAcquiredByAnotherUserError:
            return True
        self.release()

    class AlreadyAcquiredByAnotherUserError(Exception):
        pass


def mutex(
    cache_lock_id: str,
    cache_lock_timeout: int | None = None,
    skip_if_blocked: bool = False,
    identifier_attribute_name: str | None = None,
    release_check_period: float | None = None,
    bind: bool = False,
) -> "Callable":
    def decorator(func: "Callable") -> "Callable":
        @functools.wraps(func)
        async def async_run_with_mutex(*args, cache_lock_manager: "CacheLockManager", **kwargs) -> "Callable":
            result = None
            with cache_lock_manager:
                if not cache_lock_manager.is_acquired():
                    raise cache_lock_manager.AlreadyAcquiredByAnotherUserError()
                if bind:
                    kwargs["cache_lock_manager"] = cache_lock_manager
                result = await func(*args, **kwargs)
            return result

        @functools.wraps(func)
        def sync_run_with_mutex(*args, cache_lock_manager: "CacheLockManager", **kwargs) -> "Callable":
            result = None
            with cache_lock_manager:
                if not cache_lock_manager.is_acquired():
                    raise cache_lock_manager.AlreadyAcquiredByAnotherUserError()
                if bind:
                    kwargs["cache_lock_manager"] = cache_lock_manager
                result = func(*args, **kwargs)
            return result

        if asyncio.iscoroutinefunction(func):
            run_with_mutex = async_run_with_mutex
        else:
            run_with_mutex = sync_run_with_mutex

        @functools.wraps(run_with_mutex)
        def import_cache_lock_manager(*args, **kwargs):
            if identifier_attribute_name:
                identifier = getattr(args[0], identifier_attribute_name)
                cache_lock = CacheLock(f"{cache_lock_id}:{identifier}", cache_lock_timeout)
            else:
                cache_lock = CacheLock(cache_lock_id, cache_lock_timeout)
            cache_lock_manager = CacheLockManager(cache_lock, not skip_if_blocked, release_check_period)
            return run_with_mutex(cache_lock_manager=cache_lock_manager, *args, **kwargs)

        return import_cache_lock_manager

    return decorator
