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

Open `http://localhost:19080`. Access is bound to loopback because this candidate
still uses upstream demonstration administrator credentials on a fresh database.
Read the [bootstrap limitations](../docs/RELEASE-STATUS.md#initial-administrator-setup).
Do not expose this recipe as a production service.

Stop the component with:

```sh
docker compose -f recipes/compose.yaml down
```

The external database is not removed by this command. To run the published
evaluation image instead of a local build, set `CASDOOR_IMAGE` to its digest:

```sh
export CASDOOR_IMAGE=registry.thesmos.dev/thesmos/casdoor@sha256:afe7e0c8ece067a9b4ef4cf38e8e9cf108c5b7b4b96b97f335aa005b338f60d4
```

`CASDOOR_PORT` changes the host port; update the configured origin to
match. The current default image is the locally built `casdoor-integration:candidate`.

## Configuration and storage

The recipe runs as UID/GID 1000, mounts configuration read-only, drops capabilities
and supplies writable temporary storage. Theme, client and identity settings are
managed through Casdoor's UI/API and persist in PostgreSQL. See
[configuration examples](../docs/CONFIGURATION.md).

`initDataNewOnly=true` avoids replacing existing records; it does not provide
secure initial administrator setup. The recipe has no media upload volume or
durable session-store configuration. Its 384 MiB memory limit, one-CPU limit and
Go memory settings are evaluation bounds, not measured production capacity.

A shared PostgreSQL server can reduce infrastructure cost using separate databases
and roles. Give the Casdoor role no access to the Thesmos database. Database sharing
does not merge application tables or provision users automatically.
