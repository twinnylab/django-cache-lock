#################
Django cache lock
#################

`Django` 내에서 cache를 사용해 특정 구간의 코드가 동시에 실행되는 것을 방지합니다.

Quick start
-----------

#. django 프로젝트 settings의 INSTALLED_APPS 목록에 "django-cache-lock"을 추가합니다.

.. code-block:: python

    INSTALLED_APPS = [
        ...
        'django-cache-lock',
    ]
