FROM python:3.12-slim

# BuildKit will automatically set TARGETARCH to amd64, arm64, or arm
ARG TARGETARCH

# Replace the SASS_VERSION with the version you want to install
ARG SASS_VERSION=1.64.1

# Install curl and other system dependencies
RUN apt-get update && apt-get install -y \
    git \
    default-libmysqlclient-dev build-essential pkg-config \
    curl ca-certificates \
    xz-utils \
    gettext \
    && apt-get clean


# Install SASS dart (SCSS compiler)
WORKDIR /usr/local

RUN set -eux; \
    \
    # 1) map TARGETARCH → Dart Sass arch
    case "${TARGETARCH}" in \
      amd64) SASS_ARCH=x64   ;; \
      arm64) SASS_ARCH=arm64 ;; \
      arm)   SASS_ARCH=arm   ;; \
      *) echo "Unsupported arch: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    \
    # 2) download & extract directly from GitHub
    FILE=dart-sass-${SASS_VERSION}-linux-${SASS_ARCH}.tar.gz; \
    URL="https://github.com/sass/dart-sass/releases/download/${SASS_VERSION}/${FILE}"; \
    curl -fsSL "$URL" | tar -xz -C /usr/local; 

# 3) ensure it’s executable & in PATH
RUN chmod +x /usr/local/dart-sass/sass; \
    ln -sf /usr/local/dart-sass/sass /usr/local/bin/sass

# sanity check
RUN sass --version

# Install OLDP
RUN mkdir /oldp
WORKDIR /oldp

# settings
ENV DJANGO_SETTINGS_MODULE=oldp.settings
ENV DJANGO_CONFIGURATION=DevConfiguration
ENV DATABASE_URL="sqlite:///dev.db"
ENV DJANGO_SECRET_KEY=foobar12
ENV PYTHONPATH=/oldp/

# copy dependency settings
# COPY requirements.txt /oldp
# COPY ./requirements/ /oldp/requirements/
# COPY ./src/oldp/assets/static/ /oldp/src/oldp/assets/static/

# install dependencies
# RUN pip install -r requirements/prod.txt
# RUN pip install -r requirements/processing.txt
# RUN pip install -r requirements/base.txt

ADD pyproject.toml ./
RUN pip install -e ".[dev,prod,processing]"

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

