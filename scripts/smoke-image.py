#!/usr/bin/env python3
"""Test a supplied image in a disposable fixture bound only to loopback."""
import argparse
import http.cookiejar
import json
from pathlib import Path
import re
import socket
import subprocess
import time
import urllib.error
import urllib.request
import uuid

ROOT = Path(__file__).resolve().parents[1]


def docker(*args, check=True):
    return subprocess.run(["docker", *args], check=check, capture_output=True, text=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="casdoor-integration:candidate")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/image-smoke.json")
    options = parser.parse_args()
    name = "casdoor-image-smoke-" + uuid.uuid4().hex[:12]
    fixture = ROOT / ".local" / name
    fixture.mkdir(parents=True, mode=0o700)
    volume = name + "-data"
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = probe.getsockname()[1]
    base = f"http://localhost:{port}"
    config = (ROOT / "recipes/app.conf.example").read_text()
    config = re.sub(r"^driverName\s*=.*$", "driverName = sqlite", config, flags=re.M)
    config = re.sub(r"^dataSourceName\s*=.*$", "dataSourceName = file:/data/smoke.db?_pragma=busy_timeout(5000)&_pragma=journal_mode(WAL)", config, flags=re.M)
    for key in ["origin", "originFrontend"]:
        config = re.sub(r"^" + key + r"\s*=.*$", f'{key} = "{base}"', config, flags=re.M)
    (fixture / "app.conf").write_text(config)
    # A host runner need not have UID 1000. Use an owned, disposable named volume.
    image = json.loads(docker("image", "inspect", options.image).stdout)[0]
    report = {"image": image["Id"], "scope": "Disposable SQLite/loopback packaging fixture; not production acceptance", "checks": {}}

    def client():
        return urllib.request.build_opener(urllib.request.HTTPCookieProcessor(http.cookiejar.CookieJar()))

    def request(opener, path, body=None):
        data = None if body is None else json.dumps(body).encode()
        headers = {"Origin": base}
        if data is not None:
            headers["Content-Type"] = "application/json"
        with opener.open(urllib.request.Request(base + path, data=data, headers=headers), timeout=10) as response:
            raw, status = response.read(), response.status
        try:
            return status, json.loads(raw)
        except ValueError:
            return status, raw.decode()

    def ready():
        for _ in range(60):
            try:
                status, html = request(client(), "/login")
                if status == 200:
                    return html
            except (OSError, urllib.error.URLError):
                pass
            time.sleep(1)
        raise RuntimeError("Disposable image did not become ready; see ignored fixture logs")

    def login():
        opener = client()
        # These are upstream defaults, used only in this disposable local fixture.
        # Production bootstrap is a separate release gate.
        status, body = request(opener, "/api/login", {
            "type": "login", "signinMethod": "Password", "organization": "built-in",
            "username": "admin", "password": "123", "application": "app-built-in", "method": "signin",
        })
        if status != 200 or body.get("status") != "ok":
            raise RuntimeError("Disposable fixture login failed")
        return opener

    try:
        missing = docker("run", "--rm", image["Id"], check=False)
        assert missing.returncode == 1 and "Mount a readable Casdoor configuration" in missing.stderr
        report["checks"]["missing_configuration_refused"] = True
        docker("volume", "create", volume)
        docker("run", "--rm", "--user", "0", "--entrypoint", "/bin/sh", "--volume", f"{volume}:/data", image["Id"], "-ec", "chown 1000:1000 /data")
        docker("run", "-d", "--name", name, "--read-only", "--cap-drop=ALL", "--security-opt=no-new-privileges:true",
               "--pids-limit=256", "--memory=384m", "--cpus=1", "--tmpfs", "/tmp:rw,noexec,nosuid,size=32m,mode=1777",
               "--publish", f"127.0.0.1:{port}:8000", "--volume", f"{fixture}/app.conf:/conf/app.conf:ro",
               "--volume", f"{volume}:/data:rw", image["Id"])
        html = ready()
        assert isinstance(html, str) and "assets/" in html
        report["checks"]["frontend_served"] = True
        opener = login()
        status, body = request(opener, "/api/get-organization?id=admin/built-in")
        assert status == 200 and body["status"] == "ok"
        organization = body["data"]
        theme = {"themeType": "default", "colorPrimary": "#457b6a", "borderRadius": 7, "isCompact": False, "isEnabled": True}
        organization["themeData"] = theme
        status, body = request(opener, "/api/update-organization?id=admin/built-in", organization)
        assert status == 200 and body["status"] == "ok"
        report["checks"]["theme_saved"] = True
        docker("restart", name)
        ready()
        opener = login()
        status, body = request(opener, "/api/get-organization?id=admin/built-in")
        assert status == 200 and body["data"]["themeData"] == theme
        report["checks"]["theme_survives_restart"] = True
        status, body = request(opener, "/api/get-application?id=admin/app-built-in")
        assert status == 200 and body["status"] == "ok"
        application = body["data"]
        application["tokenAttributes"] = [{"name": "iss", "category": "Static Value", "type": "String", "value": "override"}]
        status, body = request(opener, "/api/update-application?id=admin/app-built-in", application)
        assert status == 200 and body["status"] == "error" and "protocol claim names" in body.get("msg", "")
        report["checks"]["reserved_claim_override_rejected"] = True
        inspection = json.loads(docker("inspect", name).stdout)[0]
        assert inspection["Config"]["User"] == "1000:1000" and inspection["HostConfig"]["ReadonlyRootfs"]
        assert set(inspection["HostConfig"]["CapDrop"]) == {"ALL"}
        report["checks"]["nonroot_readonly_runtime"] = True
    finally:
        logs = docker("logs", name, check=False)
        (fixture / "container.log").write_text(logs.stdout + logs.stderr)
        docker("rm", "-f", name, check=False)
        cleanup = docker("volume", "rm", volume, check=False)
        report["fixture_volume_removed"] = cleanup.returncode == 0
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
