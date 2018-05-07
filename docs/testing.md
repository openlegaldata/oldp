# Testing

See: https://realpython.com/blog/python/testing-in-django-part-1-best-practices-and-examples/

## Fixtures

- Django fixtures
    - https://docs.djangoproject.com/en/dev/topics/testing/tools/#topics-testing-fixtures
    - https://docs.djangoproject.com/en/dev/howto/initial-data/

```
./manage.py dumpdata
./manage.py dumpdata courts --indent 4 --output oldp/apps/courts/fixtures/courts.json
./manage.py dumpdata laws --indent 4 --output oldp/apps/laws/fixtures/laws.json


```

## App tests

- db queries (get + update + create)
- processing tests

## Browser Tests

- WebDriver / Selenium (firefox driver)
- test with local db + production db (ssh tunnel to production server)


## Coverage Integration

```
export DATABASE_URL="sqlite:///test.db"
coverage run --source='.' manage.py test

# stdout report
coverage report --omit="env/*"

# html report
coverage html --omit="env/*"
```