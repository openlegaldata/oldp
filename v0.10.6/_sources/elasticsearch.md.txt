# Elasticsearch

As search backend we rely on [Elasticsearch](http://elastic.co/). In this document we collect useful commands or queries
to work with ES.

### Propagate database entries to search index

- Rebuild index: `./manage.py rebuild_index` 
- Update existing index: `./manage.py update_index`


### Queries

```
curl -XGET localhost:9200/oldp/law/_search?pretty&query=

curl -XGET localhost:9200/oldp/law_search?pretty -d '
{
    "query": {
        "match" : {
            "book_code" : "AbwV"
        }
    },
    "sort": [
        { "doknr": { "order": "asc" } },
        "_score"
    ],
    "_source" : ["doknr", "title"]
}'

curl -XGET localhost:9200/oldp/case/_search?pretty -d '
{
    "_source" : ["text", "title"]
}'

```


#### Check cluster health

```bash
curl -XGET https://localhost:9200/_cat/health?v
```

### Load Index Mappings
```
curl -XPUT localhost:9200/leegle -d @oldp/assets/es_index.json
```
