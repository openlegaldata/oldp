# Docker

OLDP has a containerized version based on Docker. 
If you just want to try out the platform locally, this is the recommended way to do it.
The Docker image is available at [Docker Hub](https://cloud.docker.com/repository/docker/openlegaldata/oldp).


## Getting started

The OLDP web app depends services like search, db, cache.
To run all service in orchestrated fashion use `docker-compose` as following:

```
# Build & start services
docker-compose up
```

To stop the services run `docker-compose down` or press `CRTL+C`.

In beginning the database will be empty, thus, we need to create all tables in the newly created database.
```
docker exec -it oldp_app_1 python manage.py migrate
```

You have probably noticed that you set the login credentials for the MySQL database in `docker-compose.yml`.
By default, Django is using the same settings.
But if you change those, you need to adjust the `DATABASE_URL` variable.

```
export DATABASE_URL="mysql://oldp:oldp@127.0.0.1/oldp"
```



Import some demo data (from fixtures - see more in testing docs)
```
docker exec -it oldp_app_1 python manage.py loaddata \
    locations/countries.json \
    locations/states.json \
    locations/cities.json \
    courts/courts.json \
    laws/laws.json \
    cases/cases.json   
```


Compile localization files
```
docker exec -it oldp_app_1 python manage.py compilemessages --l de --l en
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
