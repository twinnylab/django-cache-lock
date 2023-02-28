# Django cache lock

Django 내에서 cache를 사용해 특정 구간의 코드가 동시에 실행되는 것을 방지합니다.

## 설정 사용

django 프로젝트의 settings를 사용하여 CacheLock의 설정을 사용하려면 INSTALLED_APPS 목록에 "django-cache-lock"을 추가합니다

``` python
INSTALLED_APPS = [
    ...
    'django-cache-lock',
]
```

프로젝트의 settings에 다음과 같이 설정을 추가할 수 있습니다.

``` python
DJANGO_CACHE_LOCK_KEY_PREFIX = "cache-lock"
DJANGO_CACHE_LOCK_RELEASE_CHECK_PERIOD = 0.1
```

### 가능한 옵션

- DJANGO_CACHE_LOCK_KEY_PREFIX (기본 값: "cache-lock"): django cache에서 key에 사용되는 접두사 입니다.
- DJANGO_CACHE_LOCK_RELEASE_CHECK_PERIOD (기본 값: 0.1): Lock 점유 시도 시 block 상태에서 다시 점유를 시도하는 주기 입니다.
