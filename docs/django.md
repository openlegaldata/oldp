# Django - Notes & Useful commands

Here you can find useful Django commands:

## Django basics

```
python manage.py runserver --insecure
python manage.py shell
python manage.py makemigrations laws
python manage.py migrate
python manage.py createsuperuser
python manage.py startapp appname
python manage.py test appname


```

## Custom commands
```
python manage.py process_laws --empty --limit 100 --min-lines 1000
python manage.py process_cases --limit 10
python manage.py import_courts --input oldp/apps/courts/data/ecli.csv --empty

```

In dev & before deployment
```

python manage.py collectstatic --noinput
python manage.py collectstatic --noinput --ignore=*.scss

./manage.py compilescss

python manage.py makemessages --locale=en --locale=de --ignore=env --ignore=workingdir
python manage.py compilemessages --l de --l en

# API token
./manage.py drf_create_token <username>

```

Migrations

```
./manage.py showmigrations

# Reset
./manage.py migrate appname --fake zero


# Login and drop tables
./manage.py dbshell

drop table cases_case;
drop table cases_relatedcase;

drop table references_casereference;
drop table references_casereferencemarker;
drop table references_lawreference;
drop table references_lawreferencemarker;


```

## Tests

```
# All tests
./manage.py test

# Specific app tests
./manage.py test oldp.apps.cases --keepdb
```