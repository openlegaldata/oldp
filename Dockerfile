# start from an official image
FROM python:3.6

# arbitrary location choice: you can change the directory
RUN mkdir /app
WORKDIR /app

# OS dependencies
RUN curl -sL https://deb.nodesource.com/setup_10.x | bash
RUN apt-get update
RUN apt-get install -y nodejs gettext

# copy our project code
COPY . /app

ENV DJANGO_SETTINGS_MODULE=oldp.settings
ENV DJANGO_CONFIGURATION=Dev
ENV DATABASE_URL="sqlite:///dev.db"
ENV DJANGO_SECRET_KEY=foobar12

# install our dependencies
RUN pip install -r requirements.txt
RUN npm install
RUN npm run-script build

RUN python manage.py collectstatic --no-input

# Locale
RUN python manage.py compilemessages --l de --l en

# expose the port 8000
EXPOSE 8000

# define the default command to run when starting the container
# gunicorn --bind 0.0.0.0:8000 oldp.wsgi:application
# " --log-file", "-", "--log-level", "debug",
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "oldp.wsgi:application"]

