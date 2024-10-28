import time
import uuid
import asyncio
import logging
import functools
import warnings
from typing import TYPE_CHECKING
from enum import Enum

from .settings import settings
from .cache_lock import CacheLock

if TYPE_CHECKING:
    from typing import Callable

logger = logging.getLogger(__name__)


class BlockOption(Enum):
    # Waits for the currently running task to complete, then executes the new request.
    # Useful when all requests must be processed sequentially without overlap.
    WAIT_FOR_COMPLETE = "WAIT_FOR_COMPLETE"

    # If a task is already running, the new request will be ignored.
    # This ensures that only the first request is processed, and any additional ones are discarded.
    IGNORE_ALL_REQUESTS = "IGNORE_ALL_REQUESTS"

    # If a task is running, all new requests are ignored until the running task completes.
    # After completion, only the latest ignored request will be executed once.
    IGNORE_AND_RUN_ONCE = "IGNORE_AND_RUN_ONCE"


class CacheLockManager:
    def __init__(
        self,
        cache_lock: CacheLock,
        # 'block' is deprecated and will be removed. Use 'block_option' instead.
        block: bool = True,
        block_option: BlockOption = BlockOption.WAIT_FOR_COMPLETE,
        release_check_period: float | None = None,
    ) -> None:
        self.cache_lock = cache_lock
        self.lock_key = str(uuid.uuid4())
        self.release_check_period: float = release_check_period or settings.RELEASE_CHECK_PERIOD
        if not block:
            warnings.warn(
                "'block' is deprecated and will be removed in a future release. "
                "Use 'block_option' instead.",
                DeprecationWarning,
                stacklevel=2
            )
            self.block_option = BlockOption.IGNORE_ALL_REQUESTS
        elif block and block_option == BlockOption.WAIT_FOR_COMPLETE:
            self.block_option = BlockOption.WAIT_FOR_COMPLETE
        else:
            self.block_option = block_option

    @property
    def state(self) -> dict:
        return {
            "cache_lock_id": self.cache_lock.id,
            "cache_lock_current_lock_key": self.cache_lock.lock_key,
            "cache_lock_manager_lock_key": self.lock_key,
            "cache_lock_manager_block_option": self.block_option,
        }

    def is_acquired(self) -> bool:
        return self.cache_lock.is_locked_by(self.lock_key)

    def acquire(self, block_option: BlockOption | None = None) -> bool:
        while True:
            if self.cache_lock.lock_with(self.lock_key):
                logger.info("CacheLock acquisition successful.", extra={"data": self.state})
                return True
            else:
                option = block_option or self.block_option
                if option == BlockOption.IGNORE_AND_RUN_ONCE and self.cache_lock.is_waiting_to_run_once:
                    logger.info(
                        "CacheLock acquisition skipped. because it is waiting to run once.",
                        extra={"data": self.state},
                    )
                    return False
                match option:
                    case BlockOption.WAIT_FOR_COMPLETE:
                        logger.info("Waiting to acquire CacheLock.", extra={"data": self.state})
                        self._sleep_until_unlock()
                        logger.info("Waiting interrupted; retrying to acquire CacheLock.", extra={"data": self.state})
                    case BlockOption.IGNORE_ALL_REQUESTS:
                        logger.info("CacheLock acquisition skipped.", extra={"data": self.state})
                        return False
                    case BlockOption.IGNORE_AND_RUN_ONCE:
                        if not self.cache_lock.set_is_waiting_to_run_once():
                            logger.info(
                                "CacheLock acquisition skipped. because it is waiting to run once.",
                                extra={"data": self.state}
                            )
                            return False
                        logger.info("Waiting to acquire CacheLock at once.", extra={"data": self.state})
                        self._sleep_until_unlock()
                        logger.info("Waiting interrupted; retrying to acquire CacheLock.", extra={"data": self.state})
                        self.cache_lock.remove_is_waiting_to_run_once()
                    case _:
                        return False

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
    # 'skip_if_blocked' is deprecated and will be removed. Use 'block_option' instead.
    skip_if_blocked: bool = False,
    block_option: BlockOption = BlockOption.WAIT_FOR_COMPLETE,
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
            if skip_if_blocked:
                warnings.warn(
                    "'skip_if_blocked' is deprecated and will be removed in a future release. "
                    "Use 'block_option' instead.",
                    DeprecationWarning,
                    stacklevel=2
                )
                option = BlockOption.IGNORE_ALL_REQUESTS
            elif not skip_if_blocked and block_option == BlockOption.WAIT_FOR_COMPLETE:
                option = BlockOption.WAIT_FOR_COMPLETE
            else:
                option = block_option
            cache_lock_manager = CacheLockManager(
                cache_lock=cache_lock,
                block_option=option,
                release_check_period=release_check_period,
            )
            return run_with_mutex(cache_lock_manager=cache_lock_manager, *args, **kwargs)

        return import_cache_lock_manager

    return decorator
