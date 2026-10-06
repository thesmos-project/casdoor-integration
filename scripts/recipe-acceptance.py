#!/usr/bin/env python3
"""Run the Compose recipe against a disposable TLS PostgreSQL database.

Checks secure startup, administrator TOTP MFA and recovery, restart persistence
and verified TLS to the database. Everything runs on loopback and is removed
afterwards; the report contains no passwords, secrets or tokens.
"""
import argparse
import base64
import hashlib
import hmac
import http.cookiejar
import json
from pathlib import Path
import re
import secrets
import shutil
import socket
import struct
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
POSTGRES_IMAGE = "postgres@sha256:91eb910c44c7ed13f7f1a4ccadaa9ca72ef14cddc04cacb6e070e48eb44731a3"


def run(*args, check=True, **kwargs):
    return subprocess.run(args, check=check, capture_output=True, text=True, **kwargs)


def totp(secret, at=None):
    key = base64.b32decode(secret.upper() + "=" * (-len(secret) % 8))
    counter = int((at or time.time()) // 30)
    digest = hmac.new(key, struct.pack(">Q", counter), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    return "%06d" % ((struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 1000000)


def wait_for_next_totp_window():
    time.sleep(30 - time.time() % 30 + 1)


class Session:
    def __init__(self, base):
        self.base = base
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def call(self, path, body=None, form=False):
        headers = {"Origin": self.base}
        data = None
        if body is not None:
            data = urllib.parse.urlencode(body).encode() if form else json.dumps(body).encode()
            headers["Content-Type"] = "application/x-www-form-urlencoded" if form else "application/json"
        request = urllib.request.Request(self.base + path, data=data, headers=headers)
        try:
            with self.opener.open(request, timeout=15) as response:
                return json.loads(response.read())
        except urllib.error.HTTPError as error:
            return {"status": "error", "http": error.code}

    def password(self, password):
        return self.call("/api/login", {"type": "login", "signinMethod": "Password", "organization": "built-in",
                                        "username": "admin", "password": password, "application": "app-built-in",
                                        "method": "signin"})

    def second_factor(self, **factor):
        return self.call("/api/login", {"type": "login", "organization": "built-in", "application": "app-built-in",
                                        "method": "signin", **factor})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="casdoor-integration:candidate")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/recipe-acceptance.json")
    options = parser.parse_args()
    nonce = secrets.token_hex(4)
    work = ROOT / ".local" / ("recipe-acceptance-" + nonce)
    deployment, certs = work / "deployment", work / "certs"
    deployment.mkdir(parents=True)
    certs.mkdir()
    network, database, project = "casdoor-recipe-" + nonce, "casdoor-recipe-db-" + nonce, "casdoor-recipe-" + nonce
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://localhost:{port}"
    report = {"image": options.image, "scope": "Disposable loopback recipe acceptance; not a capacity or HTTPS test", "checks": {}}
    compose = ["docker", "compose", "-p", project, "-f", str(ROOT / "recipes/compose.yaml"), "-f", str(work / "override.yaml")]

    def check(name, passed):
        report["checks"][name] = bool(passed)
        print(("PASS " if passed else "FAIL ") + name)
        if not passed:
            raise RuntimeError(name)

    def ready():
        for _ in range(90):
            try:
                with urllib.request.urlopen(base + "/api/get-version-info", timeout=3):
                    return
            except OSError:
                time.sleep(1)
        raise RuntimeError("Casdoor did not become ready")

    try:
        # Certificate authority and a server certificate for the database host name.
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=recipe-acceptance-ca",
            "-keyout", str(certs / "ca.key"), "-out", str(certs / "ca.pem"))
        run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=recipe-db",
            "-keyout", str(certs / "server.key"), "-out", str(certs / "server.csr"))
        (certs / "san.ext").write_text("subjectAltName=DNS:recipe-db\n")
        run("openssl", "x509", "-req", "-in", str(certs / "server.csr"), "-CA", str(certs / "ca.pem"), "-CAkey", str(certs / "ca.key"),
            "-CAcreateserial", "-days", "2", "-extfile", str(certs / "san.ext"), "-out", str(certs / "server.crt"))
        for name in ["server.key", "server.crt"]:
            (certs / name).chmod(0o644)
        db_password = secrets.token_urlsafe(24)
        (certs / "init.sql").write_text(
            f"CREATE ROLE casdoor LOGIN PASSWORD '{db_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
            "CREATE DATABASE casdoor OWNER casdoor;\nREVOKE ALL ON DATABASE casdoor FROM PUBLIC;\n")
        (certs / "init.sql").chmod(0o644)
        run("docker", "network", "create", network)
        run("docker", "run", "-d", "--name", database, "--network", network, "--network-alias", "recipe-db",
            "-e", "POSTGRES_PASSWORD=" + secrets.token_urlsafe(24), "-v", f"{certs}:/certs:ro",
            "--entrypoint", "sh", POSTGRES_IMAGE, "-c",
            "install -o postgres -m 600 /certs/server.key /var/lib/postgresql/server.key && "
            "install -o postgres -m 644 /certs/server.crt /var/lib/postgresql/server.crt && "
            "cp /certs/init.sql /docker-entrypoint-initdb.d/ && exec docker-entrypoint.sh postgres -c ssl=on "
            "-c ssl_cert_file=/var/lib/postgresql/server.crt -c ssl_key_file=/var/lib/postgresql/server.key")
        for _ in range(60):
            if run("docker", "exec", database, "psql", "-U", "postgres", "-d", "casdoor", "-Atc", "select 1", check=False).returncode == 0:
                break
            time.sleep(1)
        else:
            raise RuntimeError("PostgreSQL did not become ready")

        config = (ROOT / "recipes/app.conf.example").read_text()
        config = config.replace("REPLACE_WITH_PRIVATE_PASSWORD", db_password).replace("YOUR_DATABASE_HOST", "recipe-db")
        config = re.sub(r'^(origin|originFrontend) = .*$', lambda m: f'{m.group(1)} = "{base}"', config, flags=re.M)
        (deployment / "app.conf").write_text(config)
        shutil.copyfile(certs / "ca.pem", deployment / "db-ca.pem")
        for path in [deployment / "app.conf", deployment / "db-ca.pem"]:
            path.chmod(0o644)
        deployment.chmod(0o755)
        (work / "override.yaml").write_text(json.dumps({
            "services": {"casdoor": {"image": options.image, "volumes": [
                {"type": "bind", "source": str(deployment), "target": "/conf", "read_only": True}]}},
            "networks": {"default": {"name": network, "external": True}}}))
        env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "CASDOOR_PORT": str(port), "HOME": str(work)}

        subprocess.run(compose + ["up", "-d"], check=True, capture_output=True, env=env)
        for _ in range(60):
            state = run("docker", "compose", "-p", project, "ps", "-a", "--format", "json", env=env).stdout
            if '"exited"' in state:
                break
            time.sleep(1)
        logs = subprocess.run(compose + ["logs", "casdoor"], capture_output=True, text=True, env=env).stdout
        check("Fresh database without bootstrap secret refuses to start", "Secure startup refused" in logs)

        admin_password = secrets.token_urlsafe(24)
        (deployment / "admin-password").write_text(admin_password + "\n")
        (deployment / "admin-password").chmod(0o644)
        subprocess.run(compose + ["up", "-d", "--force-recreate"], check=True, capture_output=True, env=env)
        ready()
        check("Upstream default administrator password rejected", Session(base).password("123").get("status") != "ok")
        admin = Session(base)
        check("Bootstrap administrator password signs in", admin.password(admin_password).get("status") == "ok")
        tls = run("docker", "exec", database, "psql", "-U", "postgres", "-d", "casdoor", "-Atc",
                  "select count(*), bool_and(s.ssl) from pg_stat_ssl s join pg_stat_activity a using (pid) where a.usename='casdoor'").stdout.strip()
        connections, encrypted = tls.split("|")
        check("Casdoor connects to PostgreSQL only over verified TLS", int(connections) > 0 and encrypted == "t")

        setup = admin.call("/api/mfa/setup/initiate", {"owner": "built-in", "name": "admin", "mfaType": "app"}, form=True)
        secret, recovery = setup["data"]["secret"], setup["data"]["recoveryCodes"][0]
        verified = admin.call("/api/mfa/setup/verify", {"owner": "built-in", "name": "admin", "mfaType": "app",
                                                        "secret": secret, "passcode": totp(secret)}, form=True)
        check("TOTP enrollment verifies a current code", verified.get("status") == "ok")
        enabled = admin.call("/api/mfa/setup/enable", {"owner": "built-in", "name": "admin", "mfaType": "app",
                                                       "secret": secret, "recoveryCodes": recovery}, form=True)
        check("TOTP MFA enabled for the administrator", enabled.get("status") == "ok")

        session = Session(base)
        check("Password alone no longer completes administrator sign-in", session.password(admin_password).get("data") == "NextMfa")
        check("Wrong TOTP code rejected", session.second_factor(mfaType="app", passcode="000000" if totp(secret) != "000000" else "111111").get("status") != "ok")
        wait_for_next_totp_window()
        session = Session(base)
        session.password(admin_password)
        check("Password plus TOTP signs in", session.second_factor(mfaType="app", passcode=totp(secret)).get("status") == "ok")

        session = Session(base)
        session.password(admin_password)
        check("Recovery code signs in once", session.second_factor(recoveryCode=recovery).get("status") == "ok")
        session = Session(base)
        session.password(admin_password)
        check("Used recovery code is rejected", session.second_factor(recoveryCode=recovery).get("status") != "ok")

        replacement = secrets.token_urlsafe(24)
        (deployment / "admin-password").write_text(replacement + "\n")
        subprocess.run(compose + ["restart"], check=True, capture_output=True, env=env)
        ready()
        check("Restart with a changed secret file keeps the administrator password", Session(base).password(replacement).get("status") != "ok")
        check("MFA remains required after restart", Session(base).password(admin_password).get("data") == "NextMfa")
        # Casdoor's default abuse control: five wrong passwords freeze sign-in for 15 minutes.
        for _ in range(5):
            Session(base).password(secrets.token_urlsafe(12))
        check("Repeated wrong passwords freeze administrator sign-in", Session(base).password(admin_password).get("status") != "ok")
    finally:
        try:
            subprocess.run(compose + ["down", "--remove-orphans"], capture_output=True, env={"PATH": "/usr/local/bin:/usr/bin:/bin", "HOME": str(work)})
        except FileNotFoundError:
            pass
        run("docker", "rm", "-f", database, check=False)
        run("docker", "network", "rm", network, check=False)
        shutil.rmtree(work, ignore_errors=True)
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
