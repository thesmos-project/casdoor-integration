#!/usr/bin/env python3
"""Kubernetes recipe acceptance: recipes/kubernetes/k3s on a disposable k3s cluster.

Creates a k3d cluster, PostgreSQL with verified TLS, and a deployment overlay like
recipes/kubernetes/example with a local certificate authority. Checks the pod's
security settings, HTTPS redirection, HSTS, the OIDC issuer, Secure session
cookies, rejection of a forged forwarding header, the network policy, and
persistence of uploaded files and sessions across a restart. Set K3D and KUBECTL
to the tool paths when they are not on PATH. The report contains no secrets.
"""
import argparse
import http.client
import json
import os
from pathlib import Path
import secrets
import shutil
import socket
import ssl
import time
import uuid

from acceptance_fixture import ROOT, RecipeFixture, run

# rancher/k3s:v1.37.1-k3s1
K3S_IMAGE = "rancher/k3s@sha256:ca7f37d993d82ef0dcdcfecb2e0e2618ea541dbaffc620c8cedebe01a82acd0d"
RELEASE_IMAGE = "registry.thesmos.dev/thesmos/casdoor"


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def tool(name):
    for candidate in [os.environ.get(name.upper()), shutil.which(name), str(ROOT / ".local/tools/bin" / name)]:
        if candidate and Path(candidate).is_file():
            return candidate
    raise RuntimeError(f"{name} not found; set {name.upper()} to its path")


def image_override(image):
    if "@" in image:
        name, digest = image.split("@", 1)
        return {"name": RELEASE_IMAGE, "newName": name, "digest": digest}
    name, _, tag = image.rpartition(":")
    if not name or "/" in tag:
        name, tag = image, "latest"
    return {"name": RELEASE_IMAGE, "newName": name, "newTag": tag}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="casdoor-integration:candidate")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/kubernetes-acceptance.json")
    options = parser.parse_args()
    k3d, kubectl = tool("k3d"), tool("kubectl")
    fixture = RecipeFixture(options.image)
    cluster = fixture.network.replace("casdoor-acceptance-", "casdoor-k8s-")
    kubeconfig = fixture.work / "kubeconfig"
    https_port, http_port = free_port(), free_port()
    origin = f"https://localhost:{https_port}"
    report = {"image": options.image, "scope": "Kubernetes recipe acceptance on a disposable k3s cluster", "checks": {}}
    cluster_created = False

    def check(name, passed, detail=None):
        report["checks"][name] = bool(passed)
        print(("PASS " if passed else "FAIL ") + name)
        if not passed:
            if detail is not None:
                print("  detail:", detail)
            raise RuntimeError(name)

    def kube(*args, check=True):
        return run(kubectl, "--kubeconfig", str(kubeconfig), *args, check=check)

    try:
        fixture.start_database()
        fixture.write_config(origin=origin)
        admin_password = secrets.token_urlsafe(24)
        fixture.write_admin_password(admin_password)

        run(k3d, "cluster", "create", cluster, "--image", K3S_IMAGE, "--network", fixture.network,
            "-p", f"127.0.0.1:{https_port}:443@loadbalancer", "-p", f"127.0.0.1:{http_port}:80@loadbalancer",
            "--kubeconfig-update-default=false", "--kubeconfig-switch-context=false", "--wait", "--timeout", "300s")
        cluster_created = True
        kubeconfig.write_text(run(k3d, "kubeconfig", "get", cluster).stdout)
        run(k3d, "image", "import", options.image, "-c", cluster)
        for _ in range(180):
            if kube("get", "crd", "middlewares.traefik.io", check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("Traefik did not install its resources")

        # The overlay a deployment writes: secrets, host name, image and, for this test,
        # a Service that resolves the database's TLS name to its container.
        overlay = fixture.work / "overlay"
        overlay.mkdir()
        for name in ["app.conf", "admin-password", "db-ca.pem"]:
            shutil.copyfile(fixture.deployment / name, overlay / name)
        c = fixture.certs
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=ingress-ca",
            "-keyout", str(c / "ingress-ca.key"), "-out", str(c / "ingress-ca.pem"))
        run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=localhost",
            "-keyout", str(overlay / "tls.key"), "-out", str(c / "ingress.csr"))
        (c / "ingress.ext").write_text("subjectAltName=DNS:localhost\n")
        run("openssl", "x509", "-req", "-in", str(c / "ingress.csr"), "-CA", str(c / "ingress-ca.pem"),
            "-CAkey", str(c / "ingress-ca.key"), "-CAcreateserial", "-days", "2", "-extfile", str(c / "ingress.ext"),
            "-out", str(overlay / "tls.crt"))
        database_ip = run("docker", "inspect", "-f", "{{(index .NetworkSettings.Networks \"" + fixture.network + "\").IPAddress}}",
                          fixture.database).stdout.strip()
        (overlay / "database.yaml").write_text(json.dumps({"apiVersion": "v1", "kind": "List", "items": [
            {"apiVersion": "v1", "kind": "Service", "metadata": {"name": "recipe-db"},
             "spec": {"ports": [{"name": "postgres", "port": 5432}]}},
            {"apiVersion": "discovery.k8s.io/v1", "kind": "EndpointSlice",
             "metadata": {"name": "recipe-db", "labels": {"kubernetes.io/service-name": "recipe-db"}},
             "addressType": "IPv4", "ports": [{"name": "postgres", "port": 5432}],
             "endpoints": [{"addresses": [database_ip]}]}]}))
        host_patch = [{"op": "replace", "path": "/spec/rules/0/host", "value": "localhost"}]
        (overlay / "kustomization.yaml").write_text(json.dumps({
            "apiVersion": "kustomize.config.k8s.io/v1beta1", "kind": "Kustomization", "namespace": "casdoor",
            "resources": [os.path.relpath(ROOT / "recipes/kubernetes/k3s", overlay), "database.yaml"],
            "secretGenerator": [
                {"name": "casdoor-config", "files": ["app.conf", "admin-password", "db-ca.pem"]},
                {"name": "casdoor-tls", "type": "kubernetes.io/tls", "files": ["tls.crt", "tls.key"],
                 "options": {"disableNameSuffixHash": True}}],
            "images": [image_override(options.image)],
            "patches": [
                {"target": {"kind": "Ingress", "name": "casdoor"}, "patch": json.dumps(
                    host_patch + [{"op": "replace", "path": "/spec/tls/0/hosts/0", "value": "localhost"}])},
                {"target": {"kind": "Ingress", "name": "casdoor-http-redirect"}, "patch": json.dumps(host_patch)}]}))
        kube("apply", "-k", str(overlay))
        if kube("-n", "casdoor", "rollout", "status", "deployment/casdoor", "--timeout=300s", check=False).returncode != 0:
            raise RuntimeError("Casdoor did not become ready: " + kube("-n", "casdoor", "logs", "deployment/casdoor", "--tail=20", check=False).stdout[-800:])

        context = ssl.create_default_context(cafile=str(c / "ingress-ca.pem"))

        def raw(method, path, port=https_port, secure=True, headers=None, body=None):
            connection = (http.client.HTTPSConnection("localhost", port, timeout=10, context=context) if secure
                          else http.client.HTTPConnection("localhost", port, timeout=10))
            connection.request(method, path, body=body, headers={"Origin": origin, **(headers or {})})
            response = connection.getresponse()
            return response, response.read()

        def wait_ready():
            for _ in range(120):
                try:
                    response, _ = raw("GET", "/api/get-version-info")
                    if response.status == 200:
                        return
                except OSError:
                    pass
                time.sleep(1)
            raise RuntimeError("Casdoor is not reachable through the Ingress")

        wait_ready()
        pod = json.loads(kube("-n", "casdoor", "get", "pods", "-l", "app.kubernetes.io/name=casdoor", "-o", "json").stdout)["items"][0]
        identity = kube("-n", "casdoor", "exec", pod["metadata"]["name"], "--", "sh", "-c",
                        "id -u; touch /probe 2>/dev/null && echo writable || echo read-only").stdout.split()
        container = pod["spec"]["containers"][0]["securityContext"]
        check("Casdoor runs as a non-root user on a read-only filesystem without capabilities",
              identity == ["1000", "read-only"] and container.get("capabilities", {}).get("drop") == ["ALL"]
              and container.get("allowPrivilegeEscalation") is False, identity)

        response, _ = raw("GET", "/login", port=http_port, secure=False)
        check("HTTP redirects to HTTPS", response.status in (301, 302, 307, 308) and response.getheader("Location", "").startswith("https://"))
        response, _ = raw("GET", "/login")
        check("Certificate verifies and HSTS is sent", response.status == 200 and "max-age=" in (response.getheader("Strict-Transport-Security") or ""))
        response, data = raw("GET", "/.well-known/openid-configuration")
        check("OIDC issuer uses the HTTPS origin", json.loads(data).get("issuer") == origin)

        login = json.dumps({"type": "login", "signinMethod": "Password", "organization": "built-in", "username": "admin",
                            "password": admin_password, "application": "app-built-in", "method": "signin"})
        response, data = raw("POST", "/api/login", headers={"Content-Type": "application/json", "X-Forwarded-For": "203.0.113.9"}, body=login)
        session_cookies = [c for c in (response.headers.get_all("Set-Cookie") or []) if c.startswith("casdoor_session_id=")]
        check("Administrator signs in with the bootstrap password", json.loads(data).get("status") == "ok")
        check("Every session cookie is Secure and HttpOnly",
              session_cookies and all("; Secure" in c and "HttpOnly" in c for c in session_cookies),
              [c.split(";")[1:] for c in session_cookies])
        cookie_header = session_cookies[-1].split(";")[0]

        def api(path, payload=None):
            headers = {"Cookie": cookie_header}
            if payload is not None:
                headers["Content-Type"] = "application/json"
            _, data = raw("POST" if payload is not None else "GET", path, headers=headers,
                          body=json.dumps(payload) if payload is not None else None)
            return json.loads(data)

        user = api("/api/get-user?id=built-in/admin").get("data") or {}
        check("Forged X-Forwarded-For is not recorded as the client address",
              user.get("lastSigninIp") not in ("", None, "203.0.113.9"), user.get("lastSigninIp"))

        provider = api("/api/add-provider", {"owner": "admin", "name": "local-files", "displayName": "Local files",
                                             "category": "Storage", "type": "Local File System", "domain": origin})
        content = ("acceptance " + uuid.uuid4().hex).encode()
        boundary = uuid.uuid4().hex
        body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"check.txt\"\r\n"
                "Content-Type: text/plain\r\n\r\n").encode() + content + f"\r\n--{boundary}--\r\n".encode()
        response, data = raw("POST", "/api/upload-resource?owner=built-in&user=admin&application=app-built-in&tag=acceptance"
                             "&parent=acceptance&fullFilePath=acceptance/check.txt&provider=local-files",
                             headers={"Cookie": cookie_header, "Content-Type": "multipart/form-data; boundary=" + boundary}, body=body)
        uploaded = json.loads(data)
        file_path = "/" + uploaded.get("data", "").split(origin + "/", 1)[-1] if uploaded.get("status") == "ok" else ""
        response, data = raw("GET", file_path) if file_path else (None, b"")
        check("Uploaded file is stored and served over HTTPS", provider.get("status") == "ok" and data == content,
              {"provider": provider.get("msg"), "upload": uploaded.get("msg")})

        # Another workload in the cluster must not reach Casdoor directly; a pod that
        # matches the ingress controller's labels must, which rules out DNS or routing faults.
        def probe(name, namespace, labels=None):
            args = ["-n", namespace, "run", name, "--image", options.image, "--image-pull-policy", "IfNotPresent",
                    "--restart", "Never"]
            if labels:
                args += ["--labels", labels]
            kube(*args, "--command", "--", "sh", "-c",
                 "wget -q -T 5 -O /dev/null http://casdoor.casdoor:8000/api/health && echo reached || echo blocked")
            for _ in range(90):
                phase = kube("-n", namespace, "get", "pod", name, "-o", "jsonpath={.status.phase}", check=False).stdout
                if phase in ("Succeeded", "Failed"):
                    break
                time.sleep(1)
            return kube("-n", namespace, "logs", name, check=False).stdout

        other = probe("network-probe", "default")
        ingress_like = probe("network-probe-ingress", "kube-system", "app.kubernetes.io/name=traefik")
        check("Network policy admits only the ingress controller",
              "blocked" in other and "reached" not in other and "reached" in ingress_like,
              {"other": other[-200:], "ingress": ingress_like[-200:]})

        kube("-n", "casdoor", "rollout", "restart", "deployment/casdoor")
        kube("-n", "casdoor", "rollout", "status", "deployment/casdoor", "--timeout=300s")
        wait_ready()
        response, data = raw("GET", file_path)
        check("Uploaded file survives a restart", data == content)
        response, data = raw("GET", "/api/get-account", headers={"Cookie": cookie_header})
        check("Signed-in session survives a restart", json.loads(data).get("status") == "ok")
    finally:
        if cluster_created:
            run(k3d, "cluster", "delete", cluster, check=False)
        fixture.close()
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
