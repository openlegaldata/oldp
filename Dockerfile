# start from an official image
# FROM python:3.6
FROM python:3.10

ENV NODE_VERSION=10.20.1

# Install curl and dependencies
RUN apt-get update && apt-get install -y \
    curl \
    xz-utils \
    gettext \
    && apt-get clean

# Install node & npm
RUN curl -o- https://raw.githubusercontent.com/nvm-sh/nvm/v0.39.0/install.sh | bash
ENV NVM_DIR=/root/.nvm
RUN . "$NVM_DIR/nvm.sh" && nvm install ${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm use v${NODE_VERSION}
RUN . "$NVM_DIR/nvm.sh" && nvm alias default v${NODE_VERSION}
ENV PATH="/root/.nvm/versions/node/v${NODE_VERSION}/bin/:${PATH}"
RUN node --version
RUN npm --version

# arbitrary location choice: you can change the directory
RUN mkdir /oldp
WORKDIR /oldp

# settings
ENV DJANGO_SETTINGS_MODULE=oldp.settings
ENV DJANGO_CONFIGURATION=DevConfiguration
ENV DATABASE_URL="sqlite:///dev.db"
ENV DJANGO_SECRET_KEY=foobar12

# copy dependency settings
COPY package.json /oldp
COPY package-lock.json /oldp
COPY webpack.config.js /oldp
COPY requirements.txt /oldp
COPY ./requirements/ /oldp/requirements/
COPY ./oldp/assets/static/ /oldp/oldp/assets/static/

# install dependencies
RUN npm install
RUN npm run-script build
RUN pip install -r requirements.txt

# copy remaining project code
COPY . /oldp

# RUN python manage.py collectstatic --no-input

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

