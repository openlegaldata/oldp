# Performance Optimization Beyond Django (Gunicorn, Nginx, MariaDB, Elasticsearch, Redis)

This guide covers performance work **outside** Django application code for OLDP-style deployments.

It focuses on:

- `gunicorn` (Python app server)
- `nginx` (reverse proxy / compression / static assets)
- `MariaDB` (primary relational DB)
- `Elasticsearch` (search backend)
- `Redis` (cache backend)
- `docker compose` examples for local/prod-like setups

This document is intended as a practical checklist and starting point, not a one-size-fits-all config. Benchmark with your own traffic patterns.

## 1. Optimization Priorities (Recommended Order)

Start here before tuning individual services:

1. Measure baseline latency and throughput per endpoint group (`/`, `/case/`, `/law/`, `/api/*`, `/search/*`)
2. Separate cold vs warm cache behavior
3. Confirm where time is spent:
   - app CPU
   - DB queries
   - Elasticsearch queries
   - network / proxy overhead
4. Tune one layer at a time
5. Re-measure after each change

## 2. Gunicorn (App Server)

### Goals

- Keep worker processes busy but not overloaded
- Avoid memory bloat / worker stalls
- Reduce tail latency under burst traffic

### Recommended baseline settings

- Use `gthread` or `sync` workers (start simple)
- Preload app if startup cost is high and memory sharing helps (`--preload`)
- Limit worker lifetime to mitigate leaks (`--max-requests`, `--max-requests-jitter`)
- Set sane timeouts (avoid very high defaults masking issues)

### Example command (good starting point)

```bash
gunicorn oldp.wsgi:application \
  --bind 0.0.0.0:8000 \
  --workers 3 \
  --threads 4 \
  --worker-class gthread \
  --timeout 30 \
  --graceful-timeout 30 \
  --keep-alive 5 \
  --max-requests 1000 \
  --max-requests-jitter 100 \
  --preload \
  --access-logfile - \
  --error-logfile -
```

### Sizing guidance

- CPU-bound endpoints: fewer workers, fewer threads
- I/O-bound endpoints (DB/search/cache): moderate threads help
- Start with:
  - `workers ~= CPU cores`
  - `threads = 2..4`
- Increase gradually while monitoring:
  - p95 latency
  - memory usage per worker
  - worker restarts / timeouts

### Common mistakes

- Too many workers causing DB connection pressure
- Very high `timeout` hiding slow dependencies
- No `max-requests` in long-running processes with slow memory growth

## 3. Nginx (Reverse Proxy, Compression, Static Files)

### Goals

- Terminate client connections efficiently
- Compress text responses
- Serve static files directly
- Protect Gunicorn from slow clients

### Recommended optimizations

- Enable `gzip` (and `brotli` if available in your image)
- Cache static assets aggressively (`immutable` for hashed files)
- Proxy buffering on
- Keepalive between nginx and gunicorn
- Set request/response timeouts explicitly

### Example Nginx config (OLDP-oriented)

```nginx
server {
    listen 80;
    server_name _;

    client_max_body_size 20m;

    gzip on;
    gzip_comp_level 5;
    gzip_min_length 1024;
    gzip_types
        text/plain
        text/css
        text/javascript
        application/javascript
        application/json
        application/xml
        application/rss+xml
        image/svg+xml;
    gzip_vary on;

    location /static/ {
        alias /srv/oldp/static/;
        access_log off;
        expires 30d;
        add_header Cache-Control "public, max-age=2592000, immutable";
    }

    location /media/ {
        alias /srv/oldp/media/;
        expires 1d;
        add_header Cache-Control "public, max-age=86400";
    }

    location / {
        proxy_pass http://app:8000;
        proxy_http_version 1.1;

        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;

        proxy_connect_timeout 5s;
        proxy_send_timeout 60s;
        proxy_read_timeout 60s;

        proxy_buffering on;
        proxy_buffers 16 16k;
        proxy_busy_buffers_size 64k;

        proxy_set_header Connection "";
    }
}
```

### Optional: Nginx micro-cache (anonymous only)

If you later want edge/proxy caching for anon traffic:

- Cache only GET/HEAD
- Bypass when auth/session cookies are present
- Start with very small TTL (1-10s)

This is powerful but should be a follow-up after validating Django-side cache correctness.

## 4. MariaDB (Database)

### Goals

- Keep hot indexes/data in memory
- Avoid expensive disk flush behavior that is too strict for your workload
- Support concurrent reads from API/page traffic

### High-impact areas

- InnoDB buffer pool size
- Connection limits / thread behavior
- Slow query logging
- Correct indexes (still the biggest win after memory tuning)

### Recommended MariaDB baseline (`my.cnf` snippet)

```cnf
[mysqld]
innodb_buffer_pool_size = 1G
innodb_buffer_pool_instances = 1
innodb_log_file_size = 256M
innodb_flush_method = O_DIRECT
innodb_flush_log_at_trx_commit = 1
max_connections = 200
thread_cache_size = 50
table_open_cache = 2048

# Observability
slow_query_log = 1
long_query_time = 0.5
log_queries_not_using_indexes = 0
```

### Notes

- `innodb_buffer_pool_size` should usually be the largest memory allocation on a DB host/container.
- For dedicated DB hosts, common targets are `50-70%` of RAM.
- In containers, ensure memory limits and DB tuning agree (don’t allocate a 2G buffer pool in a 1G-limited container).

### Django/MariaDB interaction tips

- Keep `CONN_MAX_AGE` reasonable (persistent connections help, but can pin too many DB connections if gunicorn workers are oversized)
- Tune gunicorn worker count and DB `max_connections` together
- Use slow query logs to drive schema/index changes before over-tuning MariaDB globals

## 5. Elasticsearch (Search Backend)

### Goals

- Stable low-latency search queries
- Sufficient heap without over-allocation
- Predictable indexing/refresh behavior

### High-impact settings

- JVM heap size (`Xms`, `Xmx`)
- Index shard/replica counts (especially for single-node)
- Refresh interval (during heavy indexing)
- Host kernel setting: `vm.max_map_count`

### Recommended single-node dev/staging baseline

```yaml
environment:
  - discovery.type=single-node
  - xpack.security.enabled=false
  - "ES_JAVA_OPTS=-Xms1g -Xmx1g"
```

### Host requirement (important)

On the host (not usually in compose), set:

```bash
sudo sysctl -w vm.max_map_count=262144
```

Persist in `/etc/sysctl.conf` (or platform equivalent).

### Index tuning guidance (OLDP-like search)

- Single node:
  - `number_of_replicas: 0`
- Avoid too many shards for modest datasets
- During bulk indexing:
  - increase `refresh_interval` temporarily (e.g. `30s`)
  - restore after indexing

### Performance troubleshooting checklist

- Heap pressure / GC pauses
- Slow queries by field / analyzer mismatch
- Oversharding
- Disk I/O saturation
- Search timeouts causing fallback behavior in the app

## 6. Redis (Cache Backend)

### Goals

- Fast shared cache for Django page/API caching
- Predictable eviction behavior
- Optional queue/session support separation

### Recommended uses in this stack

- Django cache backend (page/API/query fragments)
- Optional rate limiting / locks
- Avoid mixing critical and disposable data in one Redis DB without policy planning

### Redis config basics

- Set `maxmemory`
- Choose an eviction policy appropriate for cache usage
  - good default for cache-only Redis: `allkeys-lru`
- Disable AOF if using Redis only as ephemeral cache (depends on ops policy)

Example `redis.conf` snippet:

```conf
maxmemory 512mb
maxmemory-policy allkeys-lru
save ""
appendonly no
```

### Django cache integration (example)

If/when switching from file/locmem to Redis in production:

```python
CACHES = {
    "default": {
        "BACKEND": "django_redis.cache.RedisCache",
        "LOCATION": "redis://redis:6379/1",
        "OPTIONS": {
            "CLIENT_CLASS": "django_redis.client.DefaultClient",
        },
        "KEY_PREFIX": "oldp",
    }
}
```

### Operational notes

- Monitor:
  - hit rate
  - memory usage
  - evictions
  - latency spikes
- Keep cache key cardinality under control (host/language/path variance is correct, but measure growth)

## 7. Docker Compose Example (Production-Like Baseline)

This is an example `docker compose` stack showing the service relationships and performance-focused defaults. Adapt paths, secrets, and image tags.

### `compose.performance.yaml`

```yaml
services:
  app:
    build: .
    command: >
      gunicorn oldp.wsgi:application
      --bind 0.0.0.0:8000
      --workers 3
      --threads 4
      --worker-class gthread
      --timeout 30
      --graceful-timeout 30
      --keep-alive 5
      --max-requests 1000
      --max-requests-jitter 100
      --preload
      --access-logfile -
      --error-logfile -
    env_file:
      - .env
    environment:
      DJANGO_SETTINGS_MODULE: oldp.settings
      DJANGO_CONFIGURATION: ProdConfiguration
      DJANGO_SECRET_KEY: ${DJANGO_SECRET_KEY}
      DATABASE_URL: mysql://oldp:${MARIADB_PASSWORD}@db/oldp
      DJANGO_ELASTICSEARCH_URL: http://search:9200/
      DJANGO_FILE_CACHE_LOCATION: /var/tmp/django_cache
      # Example: enable Redis cache if configured in settings
      # REDIS_URL: redis://redis:6379/1
    depends_on:
      db:
        condition: service_healthy
      search:
        condition: service_started
      redis:
        condition: service_started
    expose:
      - "8000"
    volumes:
      - static_data:/srv/oldp/static
      - media_data:/srv/oldp/media
      - django_cache:/var/tmp/django_cache
    restart: unless-stopped

  nginx:
    image: nginx:1.27-alpine
    depends_on:
      - app
    ports:
      - "80:80"
    volumes:
      - ./deployment/nginx/default.conf:/etc/nginx/conf.d/default.conf:ro
      - static_data:/srv/oldp/static:ro
      - media_data:/srv/oldp/media:ro
    restart: unless-stopped

  db:
    image: mariadb:lts
    environment:
      MARIADB_ROOT_PASSWORD: ${MARIADB_ROOT_PASSWORD}
      MARIADB_DATABASE: oldp
      MARIADB_USER: oldp
      MARIADB_PASSWORD: ${MARIADB_PASSWORD}
    command:
      - --innodb-buffer-pool-size=1G
      - --innodb-log-file-size=256M
      - --max-connections=200
      - --slow-query-log=1
      - --long-query-time=0.5
    volumes:
      - mariadb_data:/var/lib/mysql
    healthcheck:
      test: ["CMD", "healthcheck.sh", "--connect", "--innodb_initialized"]
      interval: 10s
      timeout: 5s
      retries: 5
      start_period: 20s
    restart: unless-stopped

  search:
    image: docker.elastic.co/elasticsearch/elasticsearch:7.17.12
    environment:
      cluster.name: oldp
      discovery.type: single-node
      xpack.security.enabled: "false"
      ES_JAVA_OPTS: "-Xms1g -Xmx1g"
    ulimits:
      memlock:
        soft: -1
        hard: -1
    volumes:
      - es_data:/usr/share/elasticsearch/data
    restart: unless-stopped

  redis:
    image: redis:7-alpine
    command: >
      redis-server
      --maxmemory 512mb
      --maxmemory-policy allkeys-lru
      --save ""
      --appendonly no
    volumes:
      - redis_data:/data
    restart: unless-stopped

volumes:
  mariadb_data:
  es_data:
  redis_data:
  static_data:
  media_data:
  django_cache:
```

## 8. Docker Compose Tuning Notes

### Resource limits (recommended)

Set explicit CPU/memory limits (compose syntax depends on runtime/orchestrator support):

- Prevent Elasticsearch heap from exceeding container memory
- Prevent MariaDB OOM kills under burst load
- Avoid noisy-neighbor behavior in shared hosts

### Separate persistent vs ephemeral volumes

- Persistent:
  - MariaDB data
  - Elasticsearch data
  - Media uploads
- Ephemeral / disposable:
  - Django file cache (if used)
  - Redis cache-only data (optional persistence)

### Healthchecks and startup ordering

Use healthchecks for:

- MariaDB
- Elasticsearch (optional `curl http://localhost:9200/_cluster/health`)

Do not assume `depends_on` alone means “ready for traffic”.

## 9. Observability and Load Testing (Recommended)

### What to monitor

- Nginx:
  - request rate
  - p95/p99 latency
  - upstream response times
  - 4xx/5xx rates
- Gunicorn:
  - worker restarts/timeouts
  - memory per worker
- MariaDB:
  - slow queries
  - buffer pool hit rate
  - connections in use
- Elasticsearch:
  - heap %
  - GC time
  - query latency
  - rejected requests
- Redis:
  - memory
  - evictions
  - hit ratio

### Load test examples

Anonymous API:

```bash
hey -z 30s -c 20 http://localhost/api/laws/
```

Frontend cached page:

```bash
hey -z 30s -c 20 http://localhost/law/gg/
```

Search endpoint (with ES available):

```bash
hey -z 30s -c 10 'http://localhost/search/?q=gg'
```

## 10. Practical Rollout Strategy

1. Move from `runserver` to `gunicorn` behind `nginx`
2. Add `Redis` for shared Django cache (if not already)
3. Tune MariaDB memory and enable slow query logs
4. Tune Elasticsearch heap and verify host `vm.max_map_count`
5. Benchmark
6. Revisit Django-level cache TTLs and variance after observing real hit rates

## 11. Checklist (Quick Reference)

- [ ] Gunicorn workers/threads sized for available CPU/RAM
- [ ] Gunicorn `max-requests` enabled
- [ ] Nginx gzip enabled
- [ ] Nginx serves static files directly
- [ ] MariaDB slow query log enabled
- [ ] MariaDB InnoDB buffer pool sized appropriately
- [ ] Elasticsearch heap set explicitly
- [ ] Host `vm.max_map_count` configured
- [ ] Redis `maxmemory` + eviction policy set
- [ ] Docker volumes split by persistence needs
- [ ] Baseline and post-change benchmarks captured

