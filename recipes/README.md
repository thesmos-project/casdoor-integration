# Deployment recipes

Each recipe runs the Casdoor integration image against an existing PostgreSQL
database, with the same security settings and secure startup.

| Recipe | Use it for |
| --- | --- |
| [compose](compose/README.md) | One server with Docker Compose: loopback for testing, or a public host name through the Caddy HTTPS overlay. |
| [kubernetes](kubernetes/README.md) | A Kubernetes cluster: a generic base and a ready overlay for k3s with Traefik. |

[app.conf.example](app.conf.example) is the Casdoor configuration template both
recipes start from. Copy it, then set the database connection and your public
address as each recipe describes.
