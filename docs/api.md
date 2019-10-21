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

- Python https://github.com/openlegaldata/oldp-sdk-python/
- Javascript https://github.com/openlegaldata/oldp-sdk-js/
- Java https://github.com/openlegaldata/oldp-sdk-java/
- PHP https://github.com/openlegaldata/oldp-sdk-php/

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

### Data dumps and bulk downloads

To export all data that is exposed over the API at once, you can use the `dump_api_data` command.

```bash
./manage.py dump_api_data ./path/to/output_dir --override 
``` 
