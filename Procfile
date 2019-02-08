release: npm run-script build && python manage.py compilemessages --l de --l en && python manage.py collectstatic --no-input
web: gunicorn oldp.wsgi --log-file -
