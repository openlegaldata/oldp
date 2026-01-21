# Open Legal Data Platform

OLDP is a Web application based on the Django framework for making legal documents (laws and court decision) accessible as open data.
It is used for processing legal text and providing a REST-API and Elasticsearch-based search engine.

## Coding style

- Follow Django best practices
- Ruff formatting for Python 3.12
- Docstrings style is google

## Testing

- Django testing via `make test` or `make test-image` for containerized tests
- Unit tests are located in the respective apps packages (oldp/apps/accounts/tests, oldp/apps/processing/tests)

## Git

- Use semantic prefix branches (feat/, fix/, chore/)
- Before commiting run `make lint` and `make test`

## Important rules

- Never read the `.env` file