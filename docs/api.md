# API

The OLDP API is based on [Django's Rest framework extension](http://www.django-rest-framework.org/) (with [Django-Rest-Swagger](https://django-rest-swagger.readthedocs.io/en/latest/)).

## Clients

Client libraries can be auto-generated with [Swagger code-gen](https://github.com/swagger-api/swagger-codegen) based on [OpenAPI specs](https://en.wikipedia.org/wiki/OpenAPI_Specification).

For example you can use the following command the generate a Python API client:

```
# Python SDK
swagger-codegen generate \
    -i https://de.openlegaldata.io/api-schema/?format=openapi \
    -l python \
    -o ../oldp-sdk-python \
    -c oldp/api/swagger_codegen.json \
    --git-user-id openlegaldata \
    --git-repo-id oldp-sdk-python \
    --release-note "Minor changes"

    [(-t <template directory> | --template-dir <template directory>)]
    [--git-repo-id <git repo id>]
```

To display configuration help run `swagger-codegen config-help -l python`.

## Swagger settings

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