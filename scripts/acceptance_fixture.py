"""Disposable recipe deployment shared by the acceptance tests.

Starts PostgreSQL with a restricted role and verified TLS on a private Docker
network, then runs the unchanged Compose recipe against it on loopback. Nothing
here prints passwords, secrets or tokens; close() removes everything created.
"""
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


def jwt_header(token):
    segment = token.split(".")[0]
    return json.loads(base64.urlsafe_b64decode(segment + "=" * (-len(segment) % 4)))


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
            try:
                return json.loads(error.read())
            except ValueError:
                return {"status": "error", "http": error.code}

    def password(self, password, username="admin"):
        return self.call("/api/login", {"type": "login", "signinMethod": "Password", "organization": "built-in",
                                        "username": username, "password": password, "application": "app-built-in",
                                        "method": "signin"})

    def second_factor(self, **factor):
        return self.call("/api/login", {"type": "login", "organization": "built-in", "application": "app-built-in",
                                        "method": "signin", **factor})


class RecipeFixture:
    def __init__(self, image, overlays=(), environment=None):
        self.image = image
        self.overlays = [str(ROOT / "recipes/compose" / name) for name in overlays]
        nonce = secrets.token_hex(4)
        self.work = ROOT / ".local" / ("acceptance-" + nonce)
        self.deployment, self.certs = self.work / "deployment", self.work / "certs"
        self.deployment.mkdir(parents=True)
        self.certs.mkdir()
        self.network = self.project = "casdoor-acceptance-" + nonce
        self.database = "casdoor-acceptance-db-" + nonce
        with socket.socket() as probe:
            probe.bind(("127.0.0.1", 0))
            self.port = probe.getsockname()[1]
        self.base = f"http://localhost:{self.port}"
        self.env = {"PATH": "/usr/local/bin:/usr/bin:/bin", "CASDOOR_PORT": str(self.port), "HOME": str(self.work), **(environment or {})}
        self.db_password = secrets.token_urlsafe(24)

    def start_database(self):
        c = self.certs
        run("openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes", "-days", "2", "-subj", "/CN=acceptance-ca",
            "-keyout", str(c / "ca.key"), "-out", str(c / "ca.pem"))
        run("openssl", "req", "-newkey", "rsa:2048", "-nodes", "-subj", "/CN=recipe-db",
            "-keyout", str(c / "server.key"), "-out", str(c / "server.csr"))
        (c / "san.ext").write_text("subjectAltName=DNS:recipe-db\n")
        run("openssl", "x509", "-req", "-in", str(c / "server.csr"), "-CA", str(c / "ca.pem"), "-CAkey", str(c / "ca.key"),
            "-CAcreateserial", "-days", "2", "-extfile", str(c / "san.ext"), "-out", str(c / "server.crt"))
        (c / "init.sql").write_text(
            f"CREATE ROLE casdoor LOGIN PASSWORD '{self.db_password}' NOSUPERUSER NOCREATEDB NOCREATEROLE;\n"
            "CREATE DATABASE casdoor OWNER casdoor;\nREVOKE ALL ON DATABASE casdoor FROM PUBLIC;\n")
        for name in ["server.key", "server.crt", "init.sql"]:
            (c / name).chmod(0o644)
        run("docker", "network", "create", self.network)
        run("docker", "run", "-d", "--name", self.database, "--network", self.network, "--network-alias", "recipe-db",
            "-e", "POSTGRES_PASSWORD=" + secrets.token_urlsafe(24), "-v", f"{c}:/certs:ro",
            "--entrypoint", "sh", POSTGRES_IMAGE, "-c",
            "install -o postgres -m 600 /certs/server.key /var/lib/postgresql/server.key && "
            "install -o postgres -m 644 /certs/server.crt /var/lib/postgresql/server.crt && "
            "cp /certs/init.sql /docker-entrypoint-initdb.d/ && exec docker-entrypoint.sh postgres -c ssl=on "
            "-c ssl_cert_file=/var/lib/postgresql/server.crt -c ssl_key_file=/var/lib/postgresql/server.key")
        for _ in range(60):
            if self.psql("select 1", check=False).returncode == 0:
                return
            time.sleep(1)
        raise RuntimeError("PostgreSQL did not become ready")

    def psql(self, sql, database="casdoor", check=True):
        return run("docker", "exec", self.database, "psql", "-U", "postgres", "-d", database, "-v", "ON_ERROR_STOP=1",
                   "-Atc", sql, check=check)

    def write_config(self, database="casdoor", origin=None):
        config = (ROOT / "recipes/app.conf.example").read_text()
        config = config.replace("REPLACE_WITH_PRIVATE_PASSWORD", self.db_password).replace("YOUR_DATABASE_HOST", "recipe-db")
        config = config.replace("dbname=casdoor", "dbname=" + database).replace("dbName = casdoor", "dbName = " + database)
        config = re.sub(r'^(origin|originFrontend) = .*$', lambda m: f'{m.group(1)} = "{origin or self.base}"', config, flags=re.M)
        (self.deployment / "app.conf").write_text(config)
        shutil.copyfile(self.certs / "ca.pem", self.deployment / "db-ca.pem")
        for path in [self.deployment / "app.conf", self.deployment / "db-ca.pem"]:
            path.chmod(0o644)
        self.deployment.chmod(0o755)

    def write_admin_password(self, value):
        path = self.deployment / "admin-password"
        path.write_text(value + "\n")
        path.chmod(0o644)

    def remove_admin_password(self):
        (self.deployment / "admin-password").unlink(missing_ok=True)

    def compose(self, *args, image=None):
        (self.work / "override.yaml").write_text(json.dumps({
            "services": {"casdoor": {"image": image or self.image, "volumes": [
                {"type": "bind", "source": str(self.deployment), "target": "/conf", "read_only": True}]}},
            "networks": {"default": {"name": self.network, "external": True}}}))
        files = [str(ROOT / "recipes/compose/compose.yaml"), *self.overlays, str(self.work / "override.yaml")]
        command = ["docker", "compose", "-p", self.project, *[part for path in files for part in ("-f", path)], *args]
        return subprocess.run(command, capture_output=True, text=True, env=self.env)

    def start(self, image=None):
        result = self.compose("up", "-d", "--force-recreate", image=image)
        if result.returncode != 0:
            raise RuntimeError("docker compose up failed: " + result.stderr.strip()[-500:])

    def logs(self):
        return self.compose("logs", "casdoor").stdout

    def wait_exited(self):
        for _ in range(60):
            if '"exited"' in run("docker", "compose", "-p", self.project, "ps", "-a", "--format", "json", env=self.env).stdout:
                return True
            time.sleep(1)
        return False

    def ready(self):
        for _ in range(90):
            try:
                with urllib.request.urlopen(self.base + "/api/get-version-info", timeout=3):
                    return
            except OSError:
                time.sleep(1)
        raise RuntimeError("Casdoor did not become ready")

    def close(self):
        if (self.work / "override.yaml").exists():
            self.compose("down", "--remove-orphans", "--volumes")
        run("docker", "rm", "-f", self.database, check=False)
        run("docker", "network", "rm", self.network, check=False)
        shutil.rmtree(self.work, ignore_errors=True)
