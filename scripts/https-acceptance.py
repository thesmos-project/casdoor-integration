#!/usr/bin/env python3
"""HTTPS recipe acceptance: recipes/compose/compose.https.yaml in front of the recipe.

Runs Caddy with its local authority for "localhost", PostgreSQL with verified
TLS, and checks HTTPS redirection, HSTS, the Secure session cookie, the OIDC
issuer, rejection of a forged forwarding header, and persistence of uploaded
files and sessions across a restart. The report contains no secrets.
"""
import argparse
import http.client
import json
from pathlib import Path
import secrets
import socket
import ssl
import time
import uuid

from acceptance_fixture import ROOT, RecipeFixture, run


def free_port():
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        return probe.getsockname()[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="casdoor-integration:candidate")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/https-acceptance.json")
    options = parser.parse_args()
    https_port, http_port = free_port(), free_port()
    fixture = RecipeFixture(options.image, overlays=["compose.https.yaml"], environment={
        "CASDOOR_DOMAIN": "localhost", "CASDOOR_HTTPS_PORT": str(https_port), "CASDOOR_HTTP_PORT": str(http_port)})
    origin = f"https://localhost:{https_port}"
    report = {"image": options.image, "scope": "Loopback HTTPS recipe acceptance with a local certificate authority", "checks": {}}

    def check(name, passed, detail=None):
        report["checks"][name] = bool(passed)
        print(("PASS " if passed else "FAIL ") + name)
        if not passed:
            if detail is not None:
                print("  detail:", detail)
            raise RuntimeError(name)

    try:
        fixture.start_database()
        fixture.write_config(origin=origin)
        admin_password = secrets.token_urlsafe(24)
        fixture.write_admin_password(admin_password)
        fixture.start()
        fixture.ready()

        # Trust Caddy's local authority, as a deployment would trust its public CA.
        ca_path = fixture.work / "caddy-root.pem"
        for _ in range(60):
            result = run("docker", "compose", "-p", fixture.project, "exec", "-T", "proxy", "cat",
                         "/data/caddy/pki/authorities/local/root.crt", check=False, env=fixture.env)
            if result.returncode == 0 and "BEGIN CERTIFICATE" in result.stdout:
                ca_path.write_text(result.stdout)
                break
            # Caddy creates its authority when it first issues the certificate.
            probe = http.client.HTTPSConnection("localhost", https_port, timeout=3, context=ssl._create_unverified_context())
            try:
                probe.request("GET", "/")
                probe.getresponse().read()
            except OSError:
                pass
            time.sleep(1)
        else:
            raise RuntimeError("Caddy local authority unavailable")
        context = ssl.create_default_context(cafile=str(ca_path))

        def raw(method, path, port=https_port, secure=True, headers=None, body=None):
            connection = (http.client.HTTPSConnection("localhost", port, timeout=10, context=context) if secure
                          else http.client.HTTPConnection("localhost", port, timeout=10))
            connection.request(method, path, body=body, headers={"Origin": origin, **(headers or {})})
            response = connection.getresponse()
            data = response.read()
            return response, data

        for _ in range(60):
            try:
                response, _ = raw("GET", "/api/get-version-info")
                if response.status == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        response, _ = raw("GET", "/login", port=http_port, secure=False)
        check("HTTP redirects to HTTPS", response.status in (301, 302, 307, 308) and response.getheader("Location", "").startswith("https://"))
        response, _ = raw("GET", "/login")
        check("Certificate verifies and HSTS is sent", response.status == 200 and "max-age=" in (response.getheader("Strict-Transport-Security") or ""))
        response, data = raw("GET", "/.well-known/openid-configuration")
        check("OIDC issuer uses the HTTPS origin", json.loads(data).get("issuer") == origin)

        login = json.dumps({"type": "login", "signinMethod": "Password", "organization": "built-in", "username": "admin",
                            "password": admin_password, "application": "app-built-in", "method": "signin"})
        response, data = raw("POST", "/api/login", headers={"Content-Type": "application/json", "X-Forwarded-For": "203.0.113.9"}, body=login)
        cookies = response.headers.get_all("Set-Cookie") or []
        session_cookies = [c for c in cookies if c.startswith("casdoor_session_id=")]
        session_cookie = session_cookies[-1] if session_cookies else ""
        check("Administrator signs in over HTTPS", json.loads(data).get("status") == "ok")
        check("Every session cookie is Secure and HttpOnly",
              session_cookies and all("; Secure" in c and "HttpOnly" in c for c in session_cookies),
              [c.split(";")[1:] for c in session_cookies])
        cookie_header = session_cookie.split(";")[0]

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

        if fixture.compose("restart", "casdoor").returncode != 0:
            raise RuntimeError("restart failed")
        for _ in range(60):
            try:
                response, _ = raw("GET", "/api/get-version-info")
                if response.status == 200:
                    break
            except OSError:
                pass
            time.sleep(1)
        response, data = raw("GET", file_path)
        check("Uploaded file survives a restart", data == content)
        response, data = raw("GET", "/api/get-account", headers={"Cookie": cookie_header})
        check("Signed-in session survives a restart", json.loads(data).get("status") == "ok")
    finally:
        fixture.close()
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
