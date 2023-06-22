import functools
from uuid import uuid4
from multiprocessing import Pool

from django.test import SimpleTestCase
from django.core.cache import cache

from django_cache_lock import CacheLock, mutex
from django_cache_lock.settings import settings


class CacheLockIntegrationTest(SimpleTestCase):
    @staticmethod
    def increase_cache_value(key: str):
        value = cache.get(key, 0)
        value += 1
        cache.set(key, value)

    @classmethod
    def increase_cache_value_with_lock(cls, cache_lock_key: str, date_key: str):
        lock = CacheLock(cache_lock_key)
        lock.acquire()
        cls.increase_cache_value(date_key)
        lock.release()

    def test_cache_lock(self):
        cache_lock_key = str(uuid4())
        date_key = "test-data-key"
        test_function = functools.partial(CacheLockIntegrationTest.increase_cache_value_with_lock, cache_lock_key)
        with Pool(10) as p:
            p.map(test_function, [date_key] * 1000)
        self.assertEqual(cache.get(date_key, 0), 1000)
        cache.delete(date_key)

    @classmethod
    def increase_cache_value_with_context_manager(cls, cache_lock_key: str, date_key: str):
        with CacheLock(cache_lock_key):
            cls.increase_cache_value(date_key)

    def test_cache_lock_with_context_manager(self):
        cache_lock_key = str(uuid4())
        date_key = "test-data-key"
        test_function = functools.partial(
            CacheLockIntegrationTest.increase_cache_value_with_context_manager,
            cache_lock_key,
        )
        with Pool(10) as p:
            p.map(test_function, [date_key] * 1000)
        self.assertEqual(cache.get(date_key, 0), 1000)
        cache.delete(date_key)

    @classmethod
    @mutex(key=str(uuid4()))
    def increase_cache_value_with_decorator(cls, date_key: str):
        cls.increase_cache_value(date_key)

    def test_cache_lock_with_decorator(self):
        date_key = "test-data-key"
        test_function = CacheLockIntegrationTest.increase_cache_value_with_decorator
        with Pool(10) as p:
            p.map(test_function, [date_key] * 1000)
        self.assertEqual(cache.get(date_key, 0), 1000)
        cache.delete(date_key)


class CacheLockUnitTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.key = str(uuid4())
        cls.cache_lock = CacheLock(key=cls.key)

    def tearDown(self) -> None:
        self.cache_lock.release()

    def test_is_locked(self):
        self.assertFalse(self.cache_lock.is_locked)

        cache_key = f"{settings.KEY_PREFIX}:{self.key}"
        cache.set(cache_key, "some-value")
        self.assertTrue(self.cache_lock.is_locked)
        cache.delete(cache_key)

    def test_is_acquired(self):
        self.assertFalse(self.cache_lock.is_acquired)

        self.cache_lock.acquire()
        self.assertTrue(self.cache_lock.is_acquired)

        self.cache_lock.release()
        self.assertFalse(self.cache_lock.is_acquired)

    def test_acquire(self):
        # 어떤 곳에서도 사용 중이지 않을 때, 잠금, 소유 상태 모두 False 입니다.
        self.assertFalse(self.cache_lock.is_locked)
        self.assertFalse(self.cache_lock.is_acquired)

        # Lock을 획득하면 잠금, 소유 상태가 True 입니다.
        self.cache_lock.acquire()
        self.assertTrue(self.cache_lock.is_locked)
        self.assertTrue(self.cache_lock.is_acquired)

        # 다른 곳에서 사용 중인 Lock에서는 잠금 상태는 True지만, 소유 상태는 False 입니다.
        another_lock = CacheLock(key=self.key)
        self.assertTrue(another_lock.is_locked)
        self.assertFalse(another_lock.is_acquired)

        self.cache_lock.release()

    def test_release(self):
        # release()를 호출하면 잠금, 소유 상태가 False가 됩니다.
        self.assertFalse(self.cache_lock.is_locked)
        self.assertFalse(self.cache_lock.is_acquired)

        self.cache_lock.acquire()
        self.assertTrue(self.cache_lock.is_locked)
        self.assertTrue(self.cache_lock.is_acquired)

        self.cache_lock.release()
        self.assertFalse(self.cache_lock.is_locked)
        self.assertFalse(self.cache_lock.is_acquired)

        # 다름 Lock에서는 잠금을 해제할 수 없습니다.
        self.cache_lock.acquire()
        self.assertTrue(self.cache_lock.is_locked)
        self.assertTrue(self.cache_lock.is_acquired)

        another_lock = CacheLock(key=self.key)
        another_lock.release()
        self.assertTrue(self.cache_lock.is_locked)
        self.assertTrue(self.cache_lock.is_acquired)

        self.cache_lock.release()

    def test_private_acquire(self):
        self.assertFalse(self.cache_lock.is_locked)
        self.assertFalse(self.cache_lock.is_acquired)

        result = self.cache_lock._acquire()
        self.assertTrue(result)
        self.assertTrue(self.cache_lock.is_locked)
        self.assertTrue(self.cache_lock.is_acquired)

        # 이미 다른 곳에서 점유 중이라면 잠글 수 없습니다.
        another_lock = CacheLock(key=self.key)
        result = another_lock._acquire()
        self.assertFalse(result)
        self.assertTrue(another_lock.is_locked)
        self.assertFalse(another_lock.is_acquired)
