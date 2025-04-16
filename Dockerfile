# start from an official image
# FROM python:3.6
# FROM python:3.10
FROM python:3.12-slim

ENV NODE_VERSION=10.20.1

# Install curl and dependencies
RUN apt-get update && apt-get install -y \
    git \
    default-libmysqlclient-dev build-essential pkg-config \
    curl \
    xz-utils \
    gettext \
    && apt-get clean


# Install SASS
WORKDIR /usr/local

# Replace the SASS_VERSION with the version you want to install
ARG SASS_VERSION=1.64.1
ARG SASS_PLATFORM="linux-arm64"
# ARG SASS_PLATFORM="linux-x64"
ARG SASS_URL="https://github.com/sass/dart-sass/releases/download/${SASS_VERSION}/dart-sass-${SASS_VERSION}-${SASS_PLATFORM}.tar.gz"

RUN curl -OL $SASS_URL

# Extract the release (if it's an archive)
RUN tar -xzf dart-sass-${SASS_VERSION}-${SASS_PLATFORM}.tar.gz

# Clean up downloaded files (optional)
RUN rm -rf dart-sass-${SASS_VERSION}-${SASS_PLATFORM}.tar.gz

ENV PATH=$PATH:/usr/local/dart-sass

# Install OLDP
RUN mkdir /oldp
WORKDIR /oldp

# settings
ENV DJANGO_SETTINGS_MODULE=oldp.settings
ENV DJANGO_CONFIGURATION=DevConfiguration
ENV DATABASE_URL="sqlite:///dev.db"
ENV DJANGO_SECRET_KEY=foobar12

# copy dependency settings
COPY requirements.txt /oldp
COPY ./requirements/ /oldp/requirements/
COPY ./oldp/assets/static/ /oldp/oldp/assets/static/

# install dependencies
RUN pip install -r requirements/prod.txt
RUN pip install -r requirements/processing.txt
RUN pip install -r requirements/base.txt

# fix for coreapi
RUN pip install setuptools

# copy remaining project code
COPY . /oldp

RUN python manage.py compress
RUN python manage.py render_html_pages
RUN python manage.py collectstatic --no-input

# Locale
# RUN python manage.py compilemessages --l de --l en

# TODO local install
RUN git clone https://github.com/openlegaldata/oldp-de.git /oldp-de && pip install -e /oldp-de

# expose the port 8000
EXPOSE 8000

# define the default command to run when starting the container
# gunicorn --bind 0.0.0.0:8000 oldp.wsgi:application
# " --log-file", "-", "--log-level", "debug",
CMD ["gunicorn", "--bind", "0.0.0.0:8000", "oldp.wsgi:application"]

