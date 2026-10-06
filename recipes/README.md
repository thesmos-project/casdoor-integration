# Local Casdoor component recipe

This starts the candidate alongside an existing deployment. It does not start or
redistribute Thesmos, create a database, or provide a production HTTPS endpoint.
Use a disposable evaluation database. The recipe binds only to local loopback
port 19080, leaving other local evaluation ports available.

```sh
mkdir -p .local/deployment
cp recipes/app.conf.example .local/deployment/app.conf
```

Edit the ignored configuration: set your PostgreSQL hostname, database, restricted
role/password, trusted CA path and correct origin. Place the PostgreSQL CA at
`.local/deployment/db-ca.pem`. The container must be able to resolve and reach
the database hostname; `localhost` inside it names the container itself. The
configuration and CA must be readable by UID 1000. Keep the password private.

```sh
python3 scripts/build-image.py
docker compose -f recipes/compose.yaml config --quiet
docker compose -f recipes/compose.yaml up -d
docker compose -f recipes/compose.yaml down
```

Configuration is mounted read-only. Supported themes, clients and identity
settings are managed through Casdoor's UI/API and persist in PostgreSQL.
`initDataNewOnly=true` avoids replacing existing records if you deliberately
configure a bootstrap import. This does not secure upstream default bootstrap
credentials: follow the [release limitations](../docs/RELEASE-STATUS.md).

The recipe has no media upload volume or durable session-store configuration.
Those need explicit storage configuration and acceptance before production.
The memory/CPU settings are evaluation limits, not a demonstrated capacity target.
After a supported image exists, set `CASDOOR_IMAGE` to its complete registry digest.

A shared PostgreSQL server can reduce infrastructure cost, with separate roles
and databases for the two applications. Give the Casdoor role no rights to the
Thesmos database. A full stack recipe depends on supported consuming-product
images and is a later acceptance step.
