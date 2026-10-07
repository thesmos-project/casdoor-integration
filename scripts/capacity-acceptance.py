#!/usr/bin/env python3
"""Measure recipe capacity under its configured memory and CPU limits.

Runs the recipe on disposable TLS PostgreSQL and drives concurrent workloads:
browser password sign-in (bcrypt), client-credentials token issuance,
introspection and public discovery/JWKS reads. Reports throughput, latency
percentiles, errors and peak container memory, and fails on errors, an
out-of-memory kill, a restart or memory above 80% of the limit.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import copy
import json
from pathlib import Path
import re
import secrets
import threading
import time

from acceptance_fixture import ROOT, RecipeFixture, Session, run

UNITS = {"B": 1, "KiB": 1024, "MiB": 1024 ** 2, "GiB": 1024 ** 3, "kB": 1000, "MB": 1000 ** 2, "GB": 1000 ** 3}


def to_bytes(text):
    match = re.match(r"([\d.]+)\s*([A-Za-z]+)", text.strip())
    return float(match.group(1)) * UNITS.get(match.group(2), 1) if match else 0.0


def percentile(values, fraction):
    ordered = sorted(values)
    return ordered[min(len(ordered) - 1, int(len(ordered) * fraction))] if ordered else 0.0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="casdoor-integration:candidate")
    parser.add_argument("--seconds", type=int, default=20)
    parser.add_argument("--concurrency", type=int, default=16)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/capacity-acceptance.json")
    parser.add_argument("--only", help="Run only the named workload")
    options = parser.parse_args()
    fixture = RecipeFixture(options.image)
    base = fixture.base
    report = {"image": options.image, "limits": {"memory": "384m", "cpus": "1.0", "GOMEMLIMIT": "256MiB", "dbMaxOpenConns": 20},
              "concurrency": options.concurrency, "seconds_per_workload": options.seconds, "workloads": {}, "checks": {}}
    admin_password, reader_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    client_id, client_secret = "capacity-" + secrets.token_hex(6), secrets.token_urlsafe(24)

    def check(name, passed, detail=None):
        report["checks"][name] = bool(passed)
        print(("PASS " if passed else "FAIL ") + name + ("" if passed or detail is None else f"  ({detail})"))

    try:
        fixture.start_database()
        fixture.write_config()
        fixture.write_admin_password(admin_password)
        fixture.start()
        fixture.ready()
        container = run("docker", "compose", "-p", fixture.project, "ps", "-q", "casdoor", env=fixture.env).stdout.strip()

        admin = Session(base)
        admin.password(admin_password)
        organization = admin.call("/api/get-organization?id=admin/built-in")["data"]
        tenant = copy.deepcopy(organization)
        tenant.update(name="capacity-org", displayName="Capacity", themeData=None)
        admin.call("/api/add-organization", tenant)
        app = copy.deepcopy(admin.call("/api/get-application?id=admin/app-built-in")["data"])
        app.update(name="capacity-app", displayName="Capacity", clientId=client_id, clientSecret=client_secret,
                   organization="capacity-org", cert="cert-built-in", tokenFormat="JWT",
                   grantTypes=["password", "client_credentials", "refresh_token"], redirectUris=[base + "/callback"],
                   failedSigninLimit=1000000)
        admin.call("/api/add-application", app)
        admin.call("/api/add-user", {"owner": "capacity-org", "name": "capacity-reader", "password": reader_password,
                                     "type": "normal-user", "signupApplication": "capacity-app"})
        token = Session(base).call("/api/login/oauth/access_token", {
            "grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}, form=True)["access_token"]

        def sign_in():
            response = Session(base).call("/api/login", {"type": "login", "signinMethod": "Password", "organization": "capacity-org",
                                                        "username": "capacity-reader", "password": reader_password,
                                                        "application": "capacity-app", "method": "signin"})
            return response.get("status") == "ok" or response.get("msg") or str(response.get("http"))

        def client_credentials():
            return "access_token" in Session(base).call("/api/login/oauth/access_token", {
                "grant_type": "client_credentials", "client_id": client_id, "client_secret": client_secret}, form=True)

        def introspect():
            response = Session(base).call("/api/login/oauth/introspect", {
                "token": token, "token_type_hint": "access_token", "client_id": client_id, "client_secret": client_secret},
                form=True)
            if response.get("active") is True:
                return True
            return "|".join(str(response.get(key)) for key in ("active", "error", "error_description", "msg", "http"))

        def discovery():
            return bool(Session(base).call("/.well-known/capacity-app/jwks").get("keys")) and \
                bool(Session(base).call("/.well-known/openid-configuration").get("issuer"))

        peak = {"bytes": 0.0, "connections": 0}
        sampling = threading.Event()

        def sample():
            while not sampling.is_set():
                usage = run("docker", "stats", "--no-stream", "--format", "{{.MemUsage}}", container, check=False).stdout
                if usage:
                    peak["bytes"] = max(peak["bytes"], to_bytes(usage.split("/")[0]))
                count = fixture.psql("select count(*) from pg_stat_activity where usename='casdoor'", check=False).stdout.strip()
                if count.isdigit():
                    peak["connections"] = max(peak["connections"], int(count))
                time.sleep(0.5)

        sampler = threading.Thread(target=sample, daemon=True)
        sampler.start()
        for name, operation in [("password sign-in", sign_in), ("client-credentials token", client_credentials),
                                ("introspection", introspect), ("discovery and JWKS", discovery)]:
            if options.only and name != options.only:
                continue
            deadline = time.time() + options.seconds
            latencies, failures, reasons = [], [0], {}
            lock = threading.Lock()

            def worker():
                while time.time() < deadline:
                    started = time.perf_counter()
                    try:
                        ok = operation()
                    except Exception as error:
                        ok = type(error).__name__
                    elapsed = (time.perf_counter() - started) * 1000
                    with lock:
                        latencies.append(elapsed)
                        if ok is not True:
                            failures[0] += 1
                            reason = str(ok)[:120]
                            reasons[reason] = reasons.get(reason, 0) + 1

            with ThreadPoolExecutor(max_workers=options.concurrency) as pool:
                for _ in range(options.concurrency):
                    pool.submit(worker)
            requests = len(latencies)
            report["workloads"][name] = {
                "requests": requests, "per_second": round(requests / options.seconds, 1), "errors": failures[0],
                "p50_ms": round(percentile(latencies, 0.50), 1), "p95_ms": round(percentile(latencies, 0.95), 1),
                "p99_ms": round(percentile(latencies, 0.99), 1), "error_reasons": reasons}
            print(name, report["workloads"][name])
        sampling.set()
        sampler.join(timeout=5)

        state = json.loads(run("docker", "inspect", container).stdout)[0]
        limit = 384 * 1024 ** 2
        report["peak_memory_mib"] = round(peak["bytes"] / 1024 ** 2, 1)
        report["peak_database_connections"] = peak["connections"]
        check("No request failed", all(w["errors"] == 0 for w in report["workloads"].values()),
              {k: w["errors"] for k, w in report["workloads"].items()})
        check("Container was not killed for memory", not state["State"]["OOMKilled"])
        check("Container did not restart", state["RestartCount"] == 0 and state["State"]["Running"])
        check("Peak memory stays below 80% of the limit", 0 < peak["bytes"] < 0.8 * limit, report["peak_memory_mib"])
        # dbMaxOpenConns=20 for the main pool, plus two for each of the two built-in policy adapters.
        check("Database connections stay within the configured pools", 0 < peak["connections"] <= 24, peak["connections"])
    finally:
        fixture.close()
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))
    if not all(report["checks"].values()) or not report["checks"]:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
