# syntax=docker/dockerfile:1@sha256:4edf897a3ffa55b89f906fc8cc78afdb3f1834cc9c7083565e611a8a7d5fe99e
ARG GO_IMAGE=golang:1.27.1-bookworm@sha256:a4f46dc39c6b0359a3e1ed86ef14d01b374cc808649679dd5fca2290e6d54202
ARG NODE_IMAGE=node:24.21.0-bookworm-slim@sha256:d6aa754f16b3197301076f047b5def2f02ea1dbbc2ca920407d46d7ec7f87b20
ARG RUNTIME_IMAGE=alpine:3.24.2@sha256:294b683cb724975bec92580e1e685676bd4b50bda910ddb8c51d4cabeaec77e6

FROM ${NODE_IMAGE} AS frontend
WORKDIR /source/web
ARG YARN_VERSION=1.22.22
ENV CYPRESS_INSTALL_BINARY=0 NODE_OPTIONS=--max-old-space-size=2048
RUN test "$(yarn --version)" = "$YARN_VERSION"
COPY .local/source/web/package.json .local/source/web/yarn.lock ./
RUN --mount=type=cache,target=/usr/local/share/.cache/yarn \
    yarn install --frozen-lockfile --network-timeout 300000
COPY .local/source/web/ ./
RUN yarn typecheck && yarn build
COPY scripts/frontend-notices.mjs /distribution-tools/scripts/frontend-notices.mjs
COPY licenses/ /distribution-tools/licenses/
RUN node /distribution-tools/scripts/frontend-notices.mjs /source/web /out/licenses/frontend /distribution-tools

FROM ${GO_IMAGE} AS backend
WORKDIR /source
ENV GOTOOLCHAIN=local GOMAXPROCS=2 GOMEMLIMIT=768MiB
COPY .local/source/go.mod .local/source/go.sum ./
RUN --mount=type=cache,target=/go/pkg/mod go mod download
COPY .local/source/ ./
ARG TARGETARCH
ARG INTEGRATION_VERSION
ARG UPSTREAM_COMMIT
RUN test "$TARGETARCH" = amd64
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=1 go test -race -p 2 ./object ./scim ./certificate ./routers \
      -run 'TestEvaluation|TestSCIM|TestGetSyncerProviderSCIM|TestSyncerSshTunnel|TestRedirectUriMatchesPattern|TestSecureCookieFilter' -count=1 \
    && CGO_ENABLED=1 go test -race -p 2 ./ldap -count=1
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 go build -p 2 -mod=readonly -trimpath -buildvcs=false \
      -ldflags="-w -s -X github.com/casdoor/casdoor/util.Version=$INTEGRATION_VERSION -X github.com/casdoor/casdoor/util.CommitId=$UPSTREAM_COMMIT" \
      -o /out/server .
COPY scripts/go-notices.py scripts/swagger-notices.py /distribution-tools/scripts/
COPY licenses/ /distribution-tools/licenses/
COPY swagger.lock.json /distribution-tools/swagger.lock.json
RUN --mount=type=cache,target=/go/pkg/mod --mount=type=cache,target=/root/.cache/go-build \
    CGO_ENABLED=0 python3 /distribution-tools/scripts/go-notices.py /source /out/licenses/backend /distribution-tools
RUN python3 /distribution-tools/scripts/swagger-notices.py /source/swagger /out/licenses/swagger /distribution-tools

FROM ${RUNTIME_IMAGE} AS runtime
RUN apk add --no-cache ca-certificates tzdata \
    && addgroup -g 1000 casdoor \
    && adduser -D -u 1000 -G casdoor casdoor \
    && mkdir -p /conf /files /logs /data /tmp \
    && chown 1000:1000 /files /logs /data \
    && mkdir -p /licenses/dependencies/os \
    && cp /lib/apk/db/installed /licenses/dependencies/os/installed-packages
WORKDIR /
ARG INTEGRATION_VERSION
ARG UPSTREAM_COMMIT
ARG INTEGRATION_REVISION
ARG PRODUCTION_APPROVED=false
LABEL org.opencontainers.image.title="Casdoor with Thesmos integration patches" \
      org.opencontainers.image.source="https://github.com/thesmos-project/casdoor-integration" \
      org.opencontainers.image.licenses="Apache-2.0" \
      org.opencontainers.image.version="${INTEGRATION_VERSION}" \
      org.opencontainers.image.revision="${INTEGRATION_REVISION}" \
      io.thesmos.casdoor.upstream.source="https://github.com/casdoor/casdoor" \
      io.thesmos.casdoor.upstream.revision="${UPSTREAM_COMMIT}" \
      io.thesmos.casdoor.production-approved="${PRODUCTION_APPROVED}"
COPY --from=backend --chmod=0755 /out/server /server
COPY --from=backend /source/swagger /swagger
COPY --from=backend /out/licenses/swagger/supplement /swagger
COPY --from=backend /out/licenses/ /licenses/dependencies/
COPY --from=frontend /out/licenses/ /licenses/dependencies/
COPY .local/os-source-kit/ /licenses/dependencies/os/source-kit/
COPY --from=frontend /source/web/build /web/build
COPY --from=backend /source/integration-provenance.json /licenses/integration-provenance.json
COPY LICENSE NOTICE /licenses/
COPY licenses/ /licenses/third-party/
COPY docker/entrypoint.sh /entrypoint.sh
ENV logConfig='{"adapter":"console","level":4}' initDataNewOnly=true secureStartup=true dbMaxOpenConns=20
# Uploads from the Local File System storage provider; mount a volume here.
RUN install -d -o 1000 -g 1000 -m 0750 /files
USER 1000:1000
EXPOSE 8000
ENTRYPOINT ["/bin/sh", "/entrypoint.sh"]
