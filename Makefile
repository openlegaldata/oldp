# Use podman or docker as container engine to build images
CONTAINER_ENGINE ?= $(shell \
  if command -v docker >/dev/null 2>&1; then \
    echo docker; \
  else \
    echo podman; \
  fi \
)

IMAGE_TAG=v2024b

.PHONY: install-package lint lint-check test test-coverage build-image test-image up up-services

install-package:
	@echo "--- 🚀 Installing project dependencies ---"
	uv pip install -e ".[dev]"

lint:
	@echo "--- 🧹 Running linters ---"
	ruff format . 			# running ruff formatting
	ruff check . --fix  	# running ruff linting

lint-check:
	@echo "--- 🧹 Check is project is linted ---"
	# Required for CI to work, otherwise it will just pass
	ruff format .						    # running ruff formatting
	ruff check **/*.py 						        # running ruff linting

test:
	@echo "--- 🧪 Running tests ---"
	python manage.py test

test-coverage:
	@echo "--- 🧪 Running tests with coverage ---"
	coverage run manage.py test
	coverage report --fail-under=80

build-image:
	@echo "--- 🔨 Building container image ---"
	$(CONTAINER_ENGINE) build -t openlegaldata/oldp:${IMAGE_TAG} -f Dockerfile .

test-image:
	@echo "--- 🔨 Building container image ---"
	$(CONTAINER_ENGINE) run --rm openlegaldata/oldp:${IMAGE_TAG} make test

push-image:
	@echo "--- 🚀 Push container image to hub ---"
	$(CONTAINER_ENGINE) push openlegaldata/oldp:${IMAGE_TAG}

up:
	@echo "--- 🚀 Container compose up: all services ---"
	$(CONTAINER_ENGINE) compose up

up-services:
	@echo "--- 🚀 Container compose up: db search (all non-app services) ---"
	$(CONTAINER_ENGINE) compose up db search

migrate:
	@echo "--- 🔨 Apply database migrations using app container ---"
	$(CONTAINER_ENGINE) compose exec app python manage.py migrate

load-dummy-data:
	@echo "--- 🔨 Load dummy data using app container ---"
	$(CONTAINER_ENGINE) compose exec app  python manage.py loaddata \
		locations/countries.json \
		locations/states.json \
		locations/cities.json \
		courts/courts.json \
		laws/laws.json \
		cases/cases.json

rebuild-index:
	@echo "--- 🔨 Rebuild search index using app container ---"
	$(CONTAINER_ENGINE) compose exec app python manage.py rebuild_index

compile-locale:
	@echo "--- 🔨 Compiling messages for localization using app container ---"
	$(CONTAINER_ENGINE) compose exec app python manage.py compilemessages --l de --l en
