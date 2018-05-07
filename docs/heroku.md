# Heroku

Deploy OLDP on Heroku:

```
heroku login
heroku create
git push heroku master
heroku config:set CONNECTION_MODE=offline
heroku config:set ES_URL=...

# to add demo data
# run from backend repo: sbin/heroku.sh

# Django
# for debugging
heroku config:set DEBUG_COLLECTSTATIC=1

# for production
heroku config:set DISABLE_COLLECTSTATIC=1

# mysql db
heroku config:set DATABASE_URL=mysql://...
```