# Docker

OLDP has a containerized version powered by Docker.

## Getting started

The OLDP web app depends services like search, db, cache.
To run all service in orchestrated fashion use `docker-compose` as following:

```
# Build & start services
docker-compose up

# In beginning the database will be empty, thus, we need to create all tables
docker exec -it oldp_app_1 python manage.py migrate

# Import some demo data (from fixtures)
docker exec -it oldp_app_1 python manage.py loaddata locations/

# Create superuser (admin, pw: admin)
docker exec -it oldp_app_1 python manage.py shell -c \
    "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'admin@example.com', 'admin')"

```

Sometimes Elasticsearch has problems writing to its data directory. To solve this, set access rights:

```
# Quick & Dirty
chmod 777 docker/data/es

# Correct user group
chown docker:docker docker/data/es
```

## Additional notes

```
# Build image from repo
docker build -t oldp .

# Tag image as latest
docker tag oldp:latest
docker tag oldp openlegaldata/oldp:latest

# Push to hub
docker push openlegaldata/oldp:latest

# Override environment variables
docker run -e DATABASE_URL="sqlite:///db/db.sqlite" -it oldp python manage.py runserver



```
