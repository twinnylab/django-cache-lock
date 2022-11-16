from django.conf import settings

USER_SETTINGS = getattr(settings, "DJANGO_CACHE_LOCK", None)

KEY_PREFIX: str = getattr(settings, "DJANGO_CACHE_LOCK_" "KEY_PREFIX", "cache-lock")
RELEASE_CHECK_PERIOD: float = getattr(settings, "DJANGO_CACHE_LOCK_RELEASE_CHECK_PERIOD", 0.1)

DEFAULTS = {
    "KEY_PREFIX": KEY_PREFIX,
    "RELEASE_CHECK_PERIOD": RELEASE_CHECK_PERIOD,
}


class Settings:
    KEY_PREFIX: str
    RELEASE_CHECK_PERIOD: float

    def __init__(self, user_settings=None, defaults=None):
        self._user_settings = user_settings or {}
        self.defaults = defaults or DEFAULTS
        self._cached_attrs = set()

    def __getattr__(self, attribute):
        if attribute not in self.defaults:
            raise AttributeError(f"Invalid DJANGO_CACHE_LOCK setting: {attribute}")
        try:
            value = self._user_settings[attribute]
        except KeyError:
            value = self.defaults[attribute]

        self._cached_attrs.add(attribute)
        setattr(self, attribute, value)
        return value


settings = Settings(USER_SETTINGS, DEFAULTS)
