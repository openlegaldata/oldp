# Testing

See: https://realpython.com/blog/python/testing-in-django-part-1-best-practices-and-examples/

## Fixtures

- Django fixtures
    - https://docs.djangoproject.com/en/dev/topics/testing/tools/#topics-testing-fixtures
    - https://docs.djangoproject.com/en/dev/howto/initial-data/

```
./manage.py dumpdata --pks 1,2,3
./manage.py dumpdata courts --indent 4 --output oldp/apps/courts/fixtures/courts.json
./manage.py dumpdata laws --indent 4 --output oldp/apps/laws/fixtures/laws.json
./manage.py dumpdata cases --indent 4 --output oldp/apps/cases/fixtures/cases.json

```

### OLDP

- Courts: BGH+EUGH+AG...
- Laws: GG, BGB, with table...
- Cases:
    - bgh,
    - ---

## App tests

- db queries (get + update + create)
- processing tests

## Browser Tests

- WebDriver / Selenium (firefox driver)
- test with local db + production db (ssh tunnel to production server)


## Coverage Integration

```
export DJANGO_CONFIGURATION=Test
coverage run --source='.' manage.py test

# stdout report
coverage report --omit="env/*"

# html report
coverage html --omit="env/*"
```
