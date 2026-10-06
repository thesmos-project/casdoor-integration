# Local Casdoor Compose recipe

This recipe starts the evaluation image on `http://localhost:19080` with an
existing PostgreSQL database. Use a disposable database. It starts Casdoor only;
run Thesmos separately. It provides neither a production HTTPS endpoint nor a
complete production stack.

## Prepare configuration

From the repository root:

```sh
mkdir -p .local/deployment
cp recipes/app.conf.example .local/deployment/app.conf
```

Create the initial administrator password; secure startup refuses to start
without it:

```sh
openssl rand -base64 24 > .local/deployment/admin-password
chmod 0644 .local/deployment/admin-password
```

Edit `.local/deployment/app.conf` with your PostgreSQL hostname, database,
restricted role/password, trusted CA path and origin. Place the PostgreSQL CA at
`.local/deployment/db-ca.pem`. PostgreSQL TLS uses `sslmode=verify-full`.
The container must resolve and reach the database host; `localhost` inside it
names the container itself. The configuration and CA must be readable by UID
1000. Keep credentials private.

## Build and start

```sh
python3 scripts/build-image.py
docker compose -f recipes/compose.yaml config --quiet
docker compose -f recipes/compose.yaml up -d
```

Open `http://localhost:19080` and sign in as `admin` in the `built-in`
organization with the password from `.local/deployment/admin-password`. See
[secure startup](../docs/CONFIGURATION.md#initial-administrator-and-secure-startup).
The recipe serves plain HTTP on loopback for evaluation; do not expose it as a
production service.

`scripts/recipe-acceptance.py` runs this recipe end to end against a disposable
PostgreSQL database with verified TLS, then removes everything it created.

Stop the component with:

```sh
docker compose -f recipes/compose.yaml down
```

The external database is not removed by this command. To run the published
evaluation image instead of a local build, set `CASDOOR_IMAGE` to its digest:

```sh
export CASDOOR_IMAGE=registry.thesmos.dev/thesmos/casdoor@sha256:fc471613688a689838e329630c508aa8902e601a6fd16967918e9d565e59bb41
```

`CASDOOR_PORT` changes the host port; update the configured origin to
match. The current default image is the locally built `casdoor-integration:candidate`.

## Configuration and storage

The recipe runs as UID/GID 1000, mounts configuration read-only, drops capabilities
and supplies writable temporary storage. Theme, client and identity settings are
managed through Casdoor's UI/API and persist in PostgreSQL. See
[configuration examples](../docs/CONFIGURATION.md).

`initDataNewOnly=true` avoids replacing existing records. The recipe has no media upload volume or
durable session-store configuration. Its 384 MiB memory limit, one-CPU limit and
Go memory settings are evaluation bounds, not measured production capacity.

A shared PostgreSQL server can reduce infrastructure cost using separate databases
and roles. Give the Casdoor role no access to the Thesmos database. Database sharing
does not merge application tables or provision users automatically.
