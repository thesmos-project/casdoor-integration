# Kubernetes recipe

These manifests run one Casdoor instance on Kubernetes behind an HTTPS Ingress,
against an existing PostgreSQL database. They use the same image and security
settings as the [Compose recipe](../compose/README.md): a non-root user, a read-only
filesystem, no capabilities, memory and CPU limits, and secure startup.

| Directory | Use |
| --- | --- |
| [base](base) | Any cluster: Deployment, Service, volumes for uploads and sessions, and an Ingress. |
| [k3s](k3s) | k3s with its bundled Traefik: the `casdoor` namespace, HTTP to HTTPS redirect, HSTS and security headers, and a network policy that lets only Traefik reach Casdoor. |
| [example](example) | The deployment you copy: your configuration secret, host name and pinned image. |

On another ingress controller, start from `base` and add that controller's
redirect and header settings. Casdoor marks its cookies `Secure` itself
(`sessionCookieSecure`), so the ingress does not need to change cookies.

## Deploy on k3s

1. Copy [example](example) to your own directory, for example `my-casdoor`, next
   to `k3s`. To keep it elsewhere, use the pinned remote base shown in its
   `kustomization.yaml`.
2. Create the three configuration files in that directory:

   ```sh
   cp ../../app.conf.example app.conf          # recipes/app.conf.example
   openssl rand -base64 32 > admin-password     # at least 16 characters
   cp /path/to/database-ca.pem db-ca.pem       # CA of your PostgreSQL server
   ```

   In `app.conf`, set `dataSourceName` to your database and keep
   `sslmode=verify-full`. Set `origin` and `originFrontend` to your public
   HTTPS address, such as `https://auth.example.com`.
3. In `kustomization.yaml`, replace `auth.example.com` with your host name. The
   image is already pinned to the current release digest; update it when you
   upgrade, using the [registry guide](../../docs/REGISTRY.md).
4. Provide the certificate in the `casdoor-tls` Secret: enable the cert-manager
   annotation in `kustomization.yaml`, or create the Secret yourself:

   ```sh
   kubectl -n casdoor create secret tls casdoor-tls --cert=tls.crt --key=tls.key
   ```

5. Apply it and wait for Casdoor:

   ```sh
   kubectl apply -k my-casdoor
   kubectl -n casdoor rollout status deployment/casdoor
   ```

Sign in as `admin` with the password from `admin-password`, then change it. The
file is used only while the account still has its default password; see
[secure startup](../../docs/CONFIGURATION.md#initial-administrator-and-secure-startup).
Changing `app.conf` and applying again restarts Casdoor with the new
configuration.

## Storage and scaling

Two volumes keep data across restarts: `casdoor-files` for uploaded files served
from `/files`, and `casdoor-sessions` for sign-in sessions. They use the
cluster's default storage class with `ReadWriteOnce` access, so the Deployment
runs one instance and replaces it on update (`Recreate`).

To run several instances, set `redisEndpoint` in `app.conf` for shared
sessions, store uploads with an object storage provider such as S3, remove the
two volumes, and raise `replicas`. Size `cpus` for the sign-in rate you expect;
see [measured capacity](../../docs/VALIDATION.md#measured-capacity).

## Network policy

The k3s overlay admits connections to Casdoor only from Traefik in
`kube-system`. Outgoing traffic stays open, because Casdoor reaches its
database, identity providers, email and webhooks. If you change the namespace
in the k3s overlay, update the `casdoor-...@kubernetescrd` middleware names in
its Ingress annotations to match.

## Test

[kubernetes-acceptance.py](../../scripts/kubernetes-acceptance.py) runs the k3s
overlay on a disposable k3d cluster with a TLS PostgreSQL database. It needs
Docker, OpenSSL, `k3d` and `kubectl`; see [validation](../../docs/VALIDATION.md).
