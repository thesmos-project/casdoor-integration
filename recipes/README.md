# Local Casdoor Compose recipe

This recipe runs one Casdoor instance against an existing PostgreSQL database.
On its own it serves `http://localhost:19080` on loopback; with the HTTPS overlay
it serves a public host name through a Caddy reverse proxy. It starts Casdoor
only; run Thesmos separately.

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
This port serves plain HTTP on loopback only; publish Casdoor through the HTTPS
overlay below.

## Serve HTTPS

Point a DNS name at the host, allow ports 80 and 443, and set `origin` and
`originFrontend` in `app.conf` to `https://` followed by that name. Then start
both files:

```sh
export CASDOOR_DOMAIN=auth.example.com
docker compose -f recipes/compose.yaml -f recipes/compose.https.yaml up -d
```

Caddy obtains and renews the certificate, redirects HTTP to HTTPS, sends HSTS
and marks Casdoor's session cookie `Secure`; Casdoor sees plain HTTP behind the
proxy and cannot set that attribute itself. Only Caddy publishes public ports.
Casdoor trusts `X-Forwarded-For` only from loopback and private addresses, which
here means the proxy; set `trustedProxies` if your network differs.
`CASDOOR_HTTP_PORT` and `CASDOOR_HTTPS_PORT` change the published ports.
[https-acceptance.py](../scripts/https-acceptance.py) tests this overlay with
Caddy's local authority for `localhost`.

`scripts/recipe-acceptance.py` runs this recipe end to end against a disposable
PostgreSQL database with verified TLS, then removes everything it created.

Stop the component with:

```sh
docker compose -f recipes/compose.yaml down
```

The external database and the storage volumes are kept. To pin the published
release to its exact digest, set `CASDOOR_IMAGE`:

```sh
export CASDOOR_IMAGE=registry.thesmos.dev/thesmos/casdoor@sha256:RELEASE_DIGEST
```

`CASDOOR_PORT` changes the host port; update the configured origin to
match. Without `CASDOOR_IMAGE`, the recipe uses the `v4.15.0-thesmos.1` release tag;
for a local build, set `CASDOOR_IMAGE=casdoor-integration:candidate`.

## Configuration and storage

The recipe runs as UID/GID 1000 with a read-only root filesystem, mounts
configuration read-only and drops capabilities. The `casdoor-files` volume holds
files uploaded through a Local File System storage provider at `/files`; the
`casdoor-sessions` volume keeps signed-in sessions across restarts. Back up both
volumes with the database. Theme, client and identity settings are
managed through Casdoor's UI/API and persist in PostgreSQL. See
[configuration examples](../docs/CONFIGURATION.md).

`initDataNewOnly=true` avoids replacing existing records.

Sessions are files in one container, so run a single Casdoor instance per
database. Within the recipe's 384 MiB and one-CPU limits, the
[capacity test](../docs/VALIDATION.md#measured-capacity) ran without errors at
about 15 password sign-ins, 50 token issues and 150 introspections per second,
peaking at 73 MiB. Password sign-in is bounded by bcrypt; raise `cpus` for higher
sign-in rates.

`dbMaxOpenConns=20` (the image default) limits Casdoor's database pool; with its
two built-in policy adapters it uses at most 24 connections. Keep the total for
all applications on a shared PostgreSQL server below its `max_connections`,
which defaults to 100.

A shared PostgreSQL server can reduce infrastructure cost using separate databases
and roles. Give the Casdoor role no access to the Thesmos database. Database sharing
does not merge application tables or provision users automatically.
