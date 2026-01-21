# Use podman or docker as container engine to build images
CONTAINER_ENGINE ?= $(shell \
  if command -v docker >/dev/null 2>&1; then \
    echo docker; \
  else \
    echo podman; \
  fi \
)

# Detect package manager (prefer uv over pip)
PYTHON_PKG_MANAGER ?= $(shell \
  if command -v uv >/dev/null 2>&1; then \
    echo "uv"; \
  else \
    echo "pip"; \
  fi \
)

IMAGE_TAG=v2024b
VENV_DIR=.venv
VENV_BIN=$(VENV_DIR)/bin
VENV_PYTHON=$(VENV_BIN)/python
VENV_PKG_MANAGER=$(VENV_BIN)/$(PYTHON_PKG_MANAGER)

.PHONY: help venv clean-venv install lint lint-check test test-coverage docs build-image test-image up up-services restart logs migrate load-dummy-data load-dummy-users rebuild-index compile-locale

help:
	@echo "Available commands:"
	@echo ""
	@echo "  make venv              - Create virtual environment ($(VENV_DIR))"
	@echo "  make clean-venv        - Remove virtual environment"
	@echo "  make install           - Install project dependencies in venv"
	@echo "  make lint              - Run linters (format + fix)"
	@echo "  make lint-check        - Check linting without fixing"
	@echo "  make test              - Run test suite"
	@echo "  make test-coverage     - Run tests with coverage report"
	@echo "  make docs              - Build documentation with Sphinx"
	@echo ""
	@echo "Container commands:"
	@echo "  make build-image       - Build container image ($(CONTAINER_ENGINE))"
	@echo "  make test-image        - Test container image"
	@echo "  make push-image        - Push container image to registry"
	@echo "  make up                - Start all services"
	@echo "  make up-services       - Start db and search services only"
	@echo "  make migrate           - Apply database migrations"
	@echo "  make load-dummy-data   - Load test fixtures"
	@echo "  make load-dummy-users  - Load dummy users (admin, user)"
	@echo "  make rebuild-index     - Rebuild search index"
	@echo "  make compile-locale    - Compile translations"

venv:
	@echo "--- 🐍 Creating virtual environment ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		python3 -m venv $(VENV_DIR); \
		echo "✅ Virtual environment created at $(VENV_DIR)"; \
		echo ""; \
		echo "To activate it, run:"; \
		echo "  source $(VENV_DIR)/bin/activate"; \
	else \
		echo "✅ Virtual environment already exists at $(VENV_DIR)"; \
	fi

clean-venv:
	@echo "--- 🗑️  Removing virtual environment ---"
	@if [ -d "$(VENV_DIR)" ]; then \
		rm -rf $(VENV_DIR); \
		echo "✅ Virtual environment removed"; \
	else \
		echo "⚠️  Virtual environment does not exist"; \
	fi

install:
	@echo "--- 🚀 Installing project dependencies ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "⚠️  Virtual environment not found. Creating it first..."; \
		$(MAKE) venv; \
	fi
	@echo "Using package manager: $(PYTHON_PKG_MANAGER)"
	@if [ "$(PYTHON_PKG_MANAGER)" = "uv" ]; then \
		uv pip install --python $(VENV_PYTHON) -e ".[dev,search,processing,docs]"; \
	else \
		$(VENV_PKG_MANAGER) install -e ".[dev,search,processing,docs]"; \
	fi
	@echo "✅ Dependencies installed in virtual environment"

lint:
	@echo "--- 🧹 Running linters ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "⚠️  Virtual environment not found. Please run 'make install' first."; \
		exit 1; \
	fi
	$(VENV_BIN)/ruff format . 			# running ruff formatting
	$(VENV_BIN)/ruff check . --fix  	# running ruff linting

lint-check:
	@echo "--- 🧹 Check is project is linted ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "⚠️  Virtual environment not found. Please run 'make install' first."; \
		exit 1; \
	fi
	# Required for CI to work, otherwise it will just pass
	$(VENV_BIN)/ruff format .						    # running ruff formatting
	$(VENV_BIN)/ruff check **/*.py 						        # running ruff linting

test:
	@echo "--- 🧪 Running tests ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "⚠️  Virtual environment not found. Please run 'make install' first."; \
		exit 1; \
	fi
	DJANGO_CONFIGURATION=TestConfiguration $(VENV_PYTHON) manage.py test

test-coverage:
	@echo "--- 🧪 Running tests with coverage ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "⚠️  Virtual environment not found. Please run 'make install' first."; \
		exit 1; \
	fi
	DJANGO_CONFIGURATION=TestConfiguration $(VENV_BIN)/coverage run manage.py test
	$(VENV_BIN)/coverage report --fail-under=80

docs:
	@echo "--- 📚 Building documentation ---"
	@if [ ! -d "$(VENV_DIR)" ]; then \
		echo "⚠️  Virtual environment not found. Please run 'make install' first."; \
		exit 1; \
	fi
	@echo "Installing docs dependencies..."
	@if [ "$(PYTHON_PKG_MANAGER)" = "uv" ]; then \
		uv pip install --python $(VENV_PYTHON) -e ".[docs]"; \
	else \
		$(VENV_PKG_MANAGER) install -e ".[docs]"; \
	fi
	@echo "Building HTML documentation..."
	@cd docs && $(MAKE) -f Makefile html SPHINXBUILD=../$(VENV_BIN)/sphinx-build
	@echo "✅ Documentation built successfully"
	@echo "📖 Open docs/_build/html/index.html in your browser to view"

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
	@echo "Web server will start at: http://localhost:8000"
	$(CONTAINER_ENGINE) compose up -d

up-services:
	@echo "--- 🚀 Container compose up: db search (all non-app services) ---"
	$(CONTAINER_ENGINE) compose up db search

down:
	@echo "--- ❌ Container compose down: all services ---"
	$(CONTAINER_ENGINE) compose down

restart:
	@echo "--- 🔄 Container compose restart: all services ---"
	$(CONTAINER_ENGINE) compose restart

logs:
	@echo "--- 📜 Container compose tailing logs ---"
	$(CONTAINER_ENGINE) compose logs -f

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

load-dummy-users:
	@echo "--- 🔨 Load dummy users using app container ---"
	$(CONTAINER_ENGINE) compose exec app python manage.py load_dummy_users

rebuild-index:
	@echo "--- 🔨 Rebuild search index using app container ---"
	$(CONTAINER_ENGINE) compose exec app python manage.py rebuild_index

compile-locale:
	@echo "--- 🔨 Compiling messages for localization using app container ---"
	$(CONTAINER_ENGINE) compose exec app python manage.py compilemessages --l de --l en
