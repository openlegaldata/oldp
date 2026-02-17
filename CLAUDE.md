# Open Legal Data Platform

OLDP is a Web application based on the Django framework for making legal documents (laws and court decision) accessible as open data.
It is used for processing legal text and providing a REST-API and Elasticsearch-based search engine.

## Coding style

- Follow Django best practices
- App-specific URLs, templates, etc. should be added to the corresponding app package (oldp/apps/<app name>)
- When changing database models make sure to create corresponding migrations (if needed run: manage.py makemigrations)
- Ruff formatting for Python 3.12
- Docstrings style is google

## Testing

- Django testing via `make test` or `make test-image` for containerized tests
- Unit tests are located in the respective apps packages (oldp/apps/accounts/tests, oldp/apps/processing/tests)

## Documentation

- Files, classes, and functions should have appropriated documentation.
- Highlevel platform documentation (API etc) are in Markdown files in the docs folder.
- When changing code, make sure to keep the corresponding documentation in sync.

## Git

- Checkout a new branch when working on a new task 
- Use semantic prefix branches (feat/, fix/, chore/)
- Before commiting run `make lint` and `make test`
- When pushing always verify if the CI passes

## Important rules

- Never read the `.env` file
