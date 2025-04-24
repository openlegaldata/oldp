# Use podman or docker as container engine to build images
CONTAINER_ENGINE ?= $(shell command -v docker >/dev/null 2>&1 && echo docker || command -v podman >/dev/null 2>&1 && echo podman)
IMAGE_TAG=v2024b

.PHONY: install-package lint lint-check test build-image test-image up up-services

install-package:
	@echo "--- 🚀 Installing project dependencies ---"
	pip install -e ".[dev]"

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

build-image:
	@echo "--- 🔨 Building container image ---"
	$(CONTAINER_ENGINE) build -t openlegaldata/oldp:${IMAGE_TAG} -f Dockerfile .

test-image:
	@echo "--- 🔨 Building container image ---"
	$(CONTAINER_ENGINE) run --rm openlegaldata/oldp:${IMAGE_TAG} make test

up:
	@echo "--- 🚀 Container compose up: all services ---"
	$(CONTAINER_ENGINE) compose up

up-services:
	@echo "--- 🚀 Container compose up: db search (all non-app services) ---"
	$(CONTAINER_ENGINE) compose up db search