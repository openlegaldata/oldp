# Start gunicorn web server
web: gunicorn oldp.wsgi --log-file -

# devDependencies are not available at release phase
#release: npm run-script build && python manage.py compilemessages --l de --l en && python manage.py collectstatic --no-input
