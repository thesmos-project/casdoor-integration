# Kubernetes recipe

These manifests run one Casdoor instance on Kubernetes behind an HTTPS Ingress,
against an existing PostgreSQL database. They use the same image and security
settings as the [Compose recipe](../compose/README.md): a non-root user, a read-only
filesystem, no capabilities, memory and CPU limits, and secure startup.

| Directory | Use |
| --- | --- |
| [base](base) | Any cluster: Deployment, Service, volumes for uploads and sessions, and an Ingress. |
| [k3s](k3s) | k3s with its bundled Traefik: the `casdoor` namespace, HTTP to HTTPS redirect, HSTS and security headers, and a network policy that lets only Traefik reach Casdoor. |
| [cert-manager](cert-manager) | Optional: a Let's Encrypt certificate that cert-manager obtains and renews automatically. |
| [example](example) | The deployment you copy: your configuration secret, host name, email address and pinned image. It uses `k3s` and `cert-manager`. |

On another ingress controller, start from `base` and add that controller's
redirect and header settings. Casdoor marks its cookies `Secure` itself
(`sessionCookieSecure`), so the ingress does not need to change cookies.

## Deploy on k3s

Before you start:

- Point a DNS name, such as `auth.example.com`, at the cluster.
- Allow ports 80 and 443 to reach Traefik. Let's Encrypt checks the domain over
  port 80; Traefik redirects every other HTTP request to HTTPS.
- Install cert-manager once per cluster:

  ```sh
  kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.21.2/cert-manager.yaml
  kubectl -n cert-manager wait --for=condition=Available deployment --all --timeout=300s
  ```

  To provide your own certificate instead, skip this; see
  [HTTPS certificates](#https-certificates).

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
3. In `kustomization.yaml`, replace `auth.example.com` with your host name and
   `admin@example.com` with the address that should receive certificate expiry
   warnings. The image is already pinned to the current release digest; update
   it when you upgrade, using the [registry guide](../../docs/REGISTRY.md).
4. Apply it, then wait for the certificate and for Casdoor:

   ```sh
   kubectl apply -k my-casdoor
   kubectl -n casdoor wait --for=condition=Ready certificate/casdoor-tls --timeout=300s
   kubectl -n casdoor rollout status deployment/casdoor
   ```

Sign in as `admin` with the password from `admin-password`, then change it. The
file is used only while the account still has its default password; see
[secure startup](../../docs/CONFIGURATION.md#initial-administrator-and-secure-startup).
Changing `app.conf` and applying again restarts Casdoor with the new
configuration.

## HTTPS certificates

With the [cert-manager](cert-manager) component, cert-manager requests the
certificate for your host name from Let's Encrypt, stores it in the `casdoor-tls`
Secret, and renews it about 30 days before it expires. Traefik uses the renewed
certificate without a restart. If the certificate does not become ready, check
`kubectl -n casdoor describe certificate casdoor-tls`; the usual causes are DNS
that does not point at the cluster yet or port 80 being blocked.

To try the setup without Let's Encrypt rate limits, switch the issuer to the
staging server named in [issuer.yaml](cert-manager/issuer.yaml), then back to
production once it works.

To use a certificate you already have, remove the `components` entry from your
`kustomization.yaml` and create the Secret yourself; you then renew it yourself:

```sh
kubectl -n casdoor create secret tls casdoor-tls --cert=tls.crt --key=tls.key
```

On an ingress controller other than Traefik, set `ingressClassName` in
[issuer.yaml](cert-manager/issuer.yaml) to that controller's class.

## Storage and scaling

Two volumes keep data across restarts: `casdoor-files` for uploaded files served
from `/files`, and `casdoor-sessions` for sign-in sessions. They use the
cluster's default storage class with `ReadWriteOnce` access, so the Deployment
runs one instance and replaces it on update (`Recreate`).

Keep one instance per database. Casdoor keeps some state in each process:
captchas from its built-in captcha provider, the cached firewall rules, and the
schedules of syncers and LDAP auto-sync. With two instances, a captcha can fail
on the other instance, a rule change applies only where it was saved, and every
scheduled import runs twice. Shared sessions in Redis do not remove these
effects.

To handle more sign-ins, raise the CPU limit: password sign-in is bounded by
bcrypt, at about 15 per second with one CPU; see
[measured capacity](../../docs/VALIDATION.md#measured-capacity). A restart or
update takes Casdoor offline for a few seconds while the new pod starts.

## Network policy

The k3s overlay admits connections to Casdoor only from Traefik in
`kube-system`. Outgoing traffic stays open, because Casdoor reaches its
database, identity providers, email and webhooks. If you change the namespace
in the k3s overlay, update the `casdoor-...@kubernetescrd` middleware names in
its Ingress annotations to match.

## Test

[kubernetes-acceptance.py](../../scripts/kubernetes-acceptance.py) runs the k3s
overlay and the cert-manager component on a disposable k3d cluster with a TLS
PostgreSQL database. A local certificate authority replaces Let's Encrypt, which
cannot reach a test cluster. It needs
Docker, OpenSSL, `k3d` and `kubectl`; see [validation](../../docs/VALIDATION.md).
