# API

The OLDP API is based on [Django's Rest framework extension](http://www.django-rest-framework.org/)
(with [Django-Rest-Swagger](https://django-rest-swagger.readthedocs.io/en/latest/)).

## Authenticating with the API

Reading our data is possible without logging in. However, be aware of a stricter throttle policy for anonymous users (see Throttle rates).
Write operators require authentication for which two methods exist:

- **Username and password**: Use HTTP BasicAuth to login with your login credentials.
- **API Key**: In your user settings you can request a specific API key that allows you to authenticating with the API.


### Throttle rates

Spending resources carefully is of high importance for a non-profit project like ours.
Hence, we limit the usage of our API as following (taken from `oldp/settings.py`):

- **Anonymous users**: 100 requests/day
- **Registered users**: 5000 requests/hour

If you need to do more requests, check out our data dumps or contact us.
Our data is meant to be share - throttling is use a matter of limited resources.

## Clients

Client libraries can be auto-generated with [Swagger code-gen](https://github.com/swagger-api/swagger-codegen)
based on [OpenAPI specs](https://en.wikipedia.org/wiki/OpenAPI_Specification).

For example you can use the following command the generate a Python API client.
Python 3.7+ support is only available in recent Swagger versions (2.4.1+):

```
export DJANGO_DIR="/your/path/to/django/app"

# cd to the directory where you want to have the client files
# cd /your/path/to/oldp-client

# Python SDK
swagger-codegen generate \
    -i ${SITE_URL}api/schema/?format=openapi \
    -l python \
    -o ${PWD} \
    -c ${DJANGO_DIR}/oldp/api/swagger_codegen.python.json \
    --git-user-id openlegaldata \
    --git-repo-id oldp-sdk-python \
    --release-note "Minor changes"

    [(-t <template directory> | --template-dir <template directory>)]
    [--git-repo-id <git repo id>]

# Run swagger-codegen with Docker
docker run --rm -v ${PWD}:/local -v ${DJANGO_DIR}:/django swaggerapi/swagger-codegen-cli:2.4.1 generate \
    -i ${SITE_URL}api/schema/?format=openapi \
    -l python \
    -o /local \
    -c /django/oldp/api/swagger_codegen.python.json \
    --git-user-id openlegaldata \
    --git-repo-id oldp-sdk-python \
    --release-note "Minor changes"
```

To display configuration help run `swagger-codegen config-help -l python`.

## Usage

### Python

Python examples can be found in our OLDP-Notebooks on [GitHub](https://github.com/openlegaldata/oldp-notebooks).

### Curl

For terminal-loving developers, `curl` is also always an option.
Examples can be found on ${SITE_URL}api/schema/.

```
# List cities
curl -X GET "${SITE_URL}api/cities/" -H  "accept: application/json" -H  "api_key: ${API_KEY}"

# Get cases from court with id=3
curl -X GET "${SITE_URL}api/cases/?court_id=3" -H  "accept: application/json" -H  "api_key: ${API_KEY}"

```

## Other notes

The following notes are useful to configure the API on your own.

### Swagger settings

```

SWAGGER_SETTINGS = {
    'exclude_url_names': [],
    'exclude_namespaces': [],
    'api_version': '0.1',
    'api_path': '/',
    'relative_paths': False,
    'enabled_methods': [
        'get',
        'post',
        'put',
        'patch',
        'delete'
    ],
    'api_key': '',
    'is_authenticated': False,
    'is_superuser': False,
    'unauthenticated_user': 'django.contrib.auth.models.AnonymousUser',
    'permission_denied_handler': None,
    'resource_access_handler': None,
    'base_path':'helloreverb.com/docs',
    'info': {
        'contact': 'apiteam@wordnik.com',
        'description': 'This is a sample server Petstore server. '
                       'You can find out more about Swagger at '
                       '<a href="http://swagger.wordnik.com">'
                       'http://swagger.wordnik.com</a> '
                       'or on irc.freenode.net, #swagger. '
                       'For this sample, you can use the api key '
                       '"special-key" to test '
                       'the authorization filters',
        'license': 'Apache 2.0',
        'licenseUrl': 'http://www.apache.org/licenses/LICENSE-2.0.html',
        'termsOfServiceUrl': 'http://helloreverb.com/terms/',
        'title': 'Swagger Sample App',
    },
    'doc_expansion': 'none',
}

```
