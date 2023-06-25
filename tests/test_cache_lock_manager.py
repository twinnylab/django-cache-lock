import uuid
import time
import functools
from multiprocessing import Process, Queue, Pool
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from django_cache_lock import CacheLock, CacheLockManager, mutex


def non_atomic_increment_cache_value(key: str):
    value = cache.get(key, 0)
    value += 1
    cache.set(key, value)


def run_with_cache_lock(cache_lock_key: str, data_key: str):
    cache_lock_manager = CacheLockManager(CacheLock(cache_lock_key, timeout=5))
    cache_lock_manager.acquire()
    non_atomic_increment_cache_value(data_key)
    cache_lock_manager.release()


def run_using_context_manager(cache_lock_key: str, data_key: str):
    with CacheLockManager(CacheLock(cache_lock_key, timeout=5)):
        non_atomic_increment_cache_value(data_key)


@mutex(str(uuid.uuid4()), cache_lock_timeout=5)
def run_using_decorator(data_key: str):
    non_atomic_increment_cache_value(data_key)


@mutex(str(uuid.uuid4()), cache_lock_timeout=5, skip_if_blocked=True)
def run_using_decorator_without_block(data_key: str):
    non_atomic_increment_cache_value(data_key)
    time.sleep(3)


class CacheLockTestClass:
    CACHE_LOCK_ID = str(uuid.uuid4())
    result_queue = Queue()

    def __init__(self, id: str):
        self._id = id

    @mutex(CACHE_LOCK_ID, cache_lock_timeout=5, identifier_attribute_name="_id")
    def run_using_decorator_with_identifier(self, data_key: str):
        non_atomic_increment_cache_value(data_key)

    @mutex(CACHE_LOCK_ID, cache_lock_timeout=5, identifier_attribute_name="_id")
    def put_data_to_result_queue_after_five_seconds(self, data_key: str):
        time.sleep(5)
        CacheLockTestClass.result_queue.put(cache.get(data_key, 0))


class CacheLockIntegrationTest(SimpleTestCase):
    def setUp(self) -> None:
        self.data_key = str(uuid.uuid4())

    def tearDown(self) -> None:
        cache.delete(self.data_key)

    def test_cache_lock(self):
        cache_lock_key = str(uuid.uuid4())
        test_function = functools.partial(run_with_cache_lock, cache_lock_key)
        with Pool(100) as process:
            process.map(test_function, [self.data_key] * 1000)
        self.assertEqual(cache.get(self.data_key, 0), 1000)

    def test_cache_lock_using_context_manager(self):
        cache_lock_key = str(uuid.uuid4())
        test_function = functools.partial(run_using_context_manager, cache_lock_key)
        with Pool(100) as process:
            process.map(test_function, [self.data_key] * 1000)
        self.assertEqual(cache.get(self.data_key, 0), 1000)

    def test_cache_lock_using_decorator(self):
        test_function = run_using_decorator
        with Pool(100) as process:
            process.map(test_function, [self.data_key] * 1000)
        self.assertEqual(cache.get(self.data_key, 0), 1000)

    def test_cache_lock_using_decorator_without_block(self):
        test_function = run_using_decorator_without_block
        with Pool(100) as process:
            process.map(test_function, [self.data_key] * 100)
        self.assertEqual(cache.get(self.data_key, 0), 1)

    def test_cache_lock_using_decorator_with_identifier(self):
        instance_a = CacheLockTestClass(id="a")
        instance_b = CacheLockTestClass(id="b")
        process = Process(target=instance_a.put_data_to_result_queue_after_five_seconds, args=(self.data_key,))
        process.start()
        for _ in range(100):
            instance_b.run_using_decorator_with_identifier(self.data_key)
        process.join()
        self.assertEqual(CacheLockTestClass.result_queue.get(block=False), 100)


class CacheLockManagerUnitTest(SimpleTestCase):
    def setUp(self) -> None:
        cache_lock_id = str(uuid.uuid4())
        cache_lock = CacheLock(id=cache_lock_id)
        self.cache_lock_manager = CacheLockManager(cache_lock)

    def tearDown(self) -> None:
        self.cache_lock_manager.release()

    def test_acquire_success(self) -> None:
        with patch.object(CacheLock, "lock_with", return_value=True) as lock_with:
            self.assertTrue(self.cache_lock_manager.acquire())

        lock_with.assert_called_once_with(self.cache_lock_manager.lock_key)

    def test_acquire_failure_no_block(self):
        self.cache_lock_manager.block = False

        with patch.object(CacheLock, "lock_with", return_value=False) as lock_with:
            self.assertFalse(self.cache_lock_manager.acquire())

        lock_with.assert_called_once_with(self.cache_lock_manager.lock_key)

    def test_acquire_failure_with_block(self):
        with patch.object(CacheLock, "lock_with", side_effect=[False, False, True]) as lock_with:
            self.assertTrue(self.cache_lock_manager.acquire())

        lock_with.assert_called_with(self.cache_lock_manager.lock_key)
        self.assertEqual(lock_with.call_count, 3)

    def test_release_success(self):
        self.assertTrue(self.cache_lock_manager.acquire())

        with (
            patch.object(CacheLock, "is_locked") as is_locked,
            patch.object(CacheLock, "unlock_with") as unlock_with,
        ):
            self.assertTrue(self.cache_lock_manager.release())

        is_locked.assert_called_once()
        unlock_with.assert_called_once_with(self.cache_lock_manager.lock_key)

    def test_release_failure_already_unlocked(self):
        self.assertFalse(self.cache_lock_manager.cache_lock.is_locked())

        with patch.object(CacheLock, "unlock_with") as unlock_with:
            self.assertFalse(self.cache_lock_manager.release())

        unlock_with.assert_not_called()

    def test_release_failure_another_lock_key(self):
        another_lock_key = str(uuid.uuid4())
        self.assertTrue(self.cache_lock_manager.cache_lock.lock_with(another_lock_key))
        self.assertTrue(self.cache_lock_manager.cache_lock.is_locked_by(another_lock_key))

        with patch.object(CacheLock, "unlock_with", return_value=False) as unlock_with:
            self.assertFalse(self.cache_lock_manager.release())

        unlock_with.assert_called_once_with(self.cache_lock_manager.lock_key)


class CacheLockMutexUnitTest(SimpleTestCase):
    def test_bind_parameter(self):
        test_lock_key = str(uuid.uuid4())

        @mutex(test_lock_key, bind=True)
        def use_with_bind_parameter(cache_lock_manager: "CacheLockManager"):
            self.assertIsInstance(cache_lock_manager, CacheLockManager)

        use_with_bind_parameter()

        @mutex(test_lock_key, bind=True)
        def use_without_bind_parameter():
            return None

        with self.assertRaises(TypeError):
            use_without_bind_parameter()
