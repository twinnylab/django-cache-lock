import uuid
from unittest.mock import patch

from django.core.cache import cache
from django.test import SimpleTestCase

from django_cache_lock import CacheLock
from django_cache_lock.settings import settings


class CacheLockUnitTest(SimpleTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.cache_lock_id = str(uuid.uuid4())
        cls.cache_lock = CacheLock(id=cls.cache_lock_id)

    def tearDown(self) -> None:
        self.cache_lock.unlock()

    def test_id_getter_property(self) -> None:
        make_cache_key = lambda id: f"{settings.CACHE_KEY_PREFIX}:{id}"

        self.assertEqual(self.cache_lock.id, self.cache_lock_id)
        self.assertEqual(self.cache_lock._cache_key, make_cache_key(self.cache_lock_id))

    def test_id_setter_property(self) -> None:
        make_cache_key = lambda id: f"{settings.CACHE_KEY_PREFIX}:{id}"
        new_cache_lock_id = str(uuid.uuid4())
        self.cache_lock.id = new_cache_lock_id

        self.assertEqual(self.cache_lock.id, new_cache_lock_id)
        self.assertEqual(self.cache_lock._cache_key, make_cache_key(new_cache_lock_id))

        # Reset data
        self.cache_lock.id = self.cache_lock_id

    def test_lock_key_property(self) -> None:
        # Test unlocked state
        self.assertIsNone(self.cache_lock.lock_key)

        # Test locked state
        lock_key = "test-lock-key"
        self.cache_lock.lock_with(lock_key)
        self.assertEqual(self.cache_lock.lock_key, lock_key)

        # Test unlocked state
        self.cache_lock.unlock()
        self.assertIsNone(self.cache_lock.lock_key)

    def test_is_locked(self) -> None:
        # Test unlocked state
        self.assertFalse(self.cache_lock.is_locked())

        # Test locked state
        self.cache_lock.lock_with("test-lock-key")
        self.assertTrue(self.cache_lock.is_locked())

        # Test unlocked state
        self.cache_lock.unlock()
        self.assertFalse(self.cache_lock.is_locked())

    def test_is_locked_by(self) -> None:
        test_lock_key = "test-lock-key"
        another_lock_key = "another-lock-key"

        # Test unlock state
        self.assertFalse(self.cache_lock.is_locked())
        self.assertFalse(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Test locked by test-lock-key
        self.cache_lock.lock_with(test_lock_key)
        self.assertTrue(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Test unlock state
        self.cache_lock.unlock()
        self.assertFalse(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Test locked by another-lock-key
        self.cache_lock.lock_with(another_lock_key)
        self.assertFalse(self.cache_lock.is_locked_by(test_lock_key))
        self.assertTrue(self.cache_lock.is_locked_by(another_lock_key))

    def test_lock_with(self) -> None:
        test_lock_key = "test-lock-key"
        another_lock_key = "another-lock-key"

        # Test lock with test-lock-key
        self.assertTrue(self.cache_lock.lock_with(test_lock_key))
        self.assertTrue(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Already locked by test-lock-key
        self.assertTrue(self.cache_lock.lock_with(test_lock_key))
        self.assertTrue(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Already locked by another-lock-key
        self.assertFalse(self.cache_lock.lock_with(another_lock_key))
        self.assertTrue(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

    def test_unlock_with(self) -> None:
        test_lock_key = "test-lock-key"
        another_lock_key = "another-lock-key"

        self.assertTrue(self.cache_lock.lock_with(test_lock_key))
        self.assertTrue(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Test unlock with test-lock-key
        self.assertTrue(self.cache_lock.unlock_with(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked())
        self.assertFalse(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

        # Already unlocked
        self.assertTrue(self.cache_lock.unlock_with(test_lock_key))

        # Test unlock with invalid key
        self.assertTrue(self.cache_lock.lock_with(test_lock_key))
        self.assertFalse(self.cache_lock.unlock_with(another_lock_key))
        self.assertTrue(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.is_locked_by(test_lock_key))
        self.assertFalse(self.cache_lock.is_locked_by(another_lock_key))

    def test_unlock(self) -> None:
        test_lock_key = str(uuid.uuid4())

        # Already unlocked
        self.assertFalse(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.unlock())

        # Test unlock
        self.assertTrue(self.cache_lock.lock_with(test_lock_key))
        self.assertTrue(self.cache_lock.is_locked())
        self.assertTrue(self.cache_lock.unlock())
        self.assertFalse(self.cache_lock.is_locked())

    def test_touch(self) -> None:
        with patch.object(cache, "touch") as touch:
            self.cache_lock.touch()

        touch.assert_called_once_with(self.cache_lock._cache_key, None)

        with patch.object(cache, "touch") as touch:
            self.cache_lock.touch(5)

        touch.assert_called_once_with(self.cache_lock._cache_key, 5)
