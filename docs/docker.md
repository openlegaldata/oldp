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
```
