# API Swagger

We use Swagger to generate API clients for several programming languages.

## Clients generator

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

# Javascript
docker run --rm -v ${PWD}:/local -v ${DJANGO_DIR}:/django swaggerapi/swagger-codegen-cli:2.4.1 generate \
    -i ${SITE_URL}api/schema/?format=openapi \
    -l javascript \
    -o /local \
    -c /django/oldp/api/swagger_codegen.javascript.json \
    --git-user-id openlegaldata \
    --git-repo-id oldp-sdk-javascript

# Java
docker run --rm -v ${PWD}:/local -v ${DJANGO_DIR}:/django swaggerapi/swagger-codegen-cli:2.4.1 generate \
    -i ${SITE_URL}api/schema/?format=openapi \
    -l java \
    -o /local \
    -c /django/oldp/api/swagger_codegen.java.json \
    --git-user-id openlegaldata \
    --git-repo-id oldp-sdk-java
```

To display configuration help run `swagger-codegen config-help -l python`.


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
