# Docker & Podman

OLDP has a containerized version based on Docker or Podman. 
If you just want to try out the platform locally, this is the recommended way to do it.
The Docker image is available at [Github package registry](https://github.com/openlegaldata/oldp/pkgs/container/oldp).


## Getting started

The OLDP web app depends services like search, db, cache.
To run all service in orchestrated fashion use `docker compose` or `podman compose`, or use the commands from the `Makefile` as following:

```bash
# Build & start services (calls podman/docker compose up)
make up

# Web server will start at: http://localhost:8000
```

To stop the services run `make down` or press `CRTL+C`.

In beginning the database will be empty, thus, we need to create all tables in the newly created database.
```bash
make migrate
```

You have probably noticed that you set the login credentials for the MySQL database in `docker-compose.yaml`.
By default, Django is using the same settings.
But if you change those, you need to adjust the `DATABASE_URL` variable.

```bash
export DATABASE_URL="mysql://oldp:oldp@127.0.0.1/oldp"
```

Import some dummy data (from fixtures - see more in testing docs)
```bash
make load-dummy-data
```

Rebuild search index:
```bash
make rebuild-index
```


Compile localization files
```bash
make compile-locale


```

Create superuser (admin, pw: admin)
```
docker exec -it oldp_app_1 python manage.py shell -c \
    "from django.contrib.auth.models import User; User.objects.create_superuser('admin', 'admin@example.com', 'admin')"
```



## Common issues

### Old image version

If you encounter any problems, please pull the latest image first.

```bash
docker pull openlegaldata/oldp:latest
```

### Invalid file system permissions
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
# - locally
docker tag oldp:latest  

# - hub
docker tag oldp openlegaldata/oldp:latest  

# Push to hub
docker push openlegaldata/oldp:latest

# Start a container
docker run oldp

# Override environment variables
docker run -e DATABASE_URL="sqlite:///db/db.sqlite" -it oldp python manage.py runserver



```
