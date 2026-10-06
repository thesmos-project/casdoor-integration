#!/usr/bin/env python3
"""Upgrade, rollback, key-rotation and backup-restore acceptance for the recipe.

Starts the previous release on disposable TLS PostgreSQL, creates real state,
then upgrades to the candidate, rolls back, upgrades again, rotates the JWT
signing key with a retained previous key, and restores a database backup into a
fresh database. Earlier tokens and settings are checked after each step. The
report contains no passwords, secrets or tokens.
"""
import argparse
import copy
import json
from pathlib import Path
import secrets
import time

from acceptance_fixture import ROOT, RecipeFixture, Session, jwt_header, run

# The latest published release; the candidate is the locally built image.
PREVIOUS = "registry.thesmos.dev/thesmos/casdoor@sha256:fc471613688a689838e329630c508aa8902e601a6fd16967918e9d565e59bb41"
CANDIDATE = "casdoor-integration:candidate"
THEME = {"themeType": "default", "colorPrimary": "#2f6f5e", "borderRadius": 9, "isCompact": False, "isEnabled": True}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--previous", default=PREVIOUS)
    parser.add_argument("--image", default=CANDIDATE)
    parser.add_argument("--output", type=Path, default=ROOT / ".local/upgrade-acceptance.json")
    options = parser.parse_args()
    report = {"previous": options.previous, "image": options.image,
              "scope": "Disposable loopback upgrade/rollback/rotation/restore acceptance on PostgreSQL with TLS", "checks": {}}
    fixture = RecipeFixture(options.image)
    base = fixture.base
    admin_password, reader_password = secrets.token_urlsafe(24), secrets.token_urlsafe(24)
    client_id, client_secret = "upgrade-" + secrets.token_hex(6), secrets.token_urlsafe(24)

    def check(name, passed, detail=None):
        report["checks"][name] = bool(passed)
        print(("PASS " if passed else "FAIL ") + name)
        if not passed:
            if detail is not None:
                print("  detail:", detail)
            raise RuntimeError(name)

    def admin():
        session = Session(base)
        if session.password(admin_password).get("status") != "ok":
            raise RuntimeError("administrator sign-in failed")
        return session

    def issue():
        result = Session(base).call("/api/login/oauth/access_token", {
            "grant_type": "password", "client_id": client_id, "client_secret": client_secret,
            "username": "upgrade-reader", "password": reader_password, "scope": "openid profile"}, form=True)
        if "access_token" not in result:
            raise RuntimeError("token issuance failed")
        return result

    def active(token):
        return Session(base).call("/api/login/oauth/introspect", {
            "token": token, "token_type_hint": "access_token", "client_id": client_id, "client_secret": client_secret}, form=True).get("active") is True

    def refresh(token):
        return "access_token" in Session(base).call("/api/login/oauth/access_token", {
            "grant_type": "refresh_token", "client_id": client_id, "client_secret": client_secret,
            "refresh_token": token["refresh_token"]}, form=True)

    def jwks():
        keys = Session(base).call("/.well-known/upgrade-app/jwks").get("keys", [])
        return sorted((key.get("kid"), key.get("n")) for key in keys)

    def theme():
        return admin().call("/api/get-organization?id=admin/built-in")["data"].get("themeData")

    def application(session):
        return session.call("/api/get-application?id=admin/upgrade-app")["data"]

    def switch(image, label):
        fixture.start(image)
        fixture.ready()
        check(label + " starts on the existing database without a bootstrap secret", admin() is not None)

    try:
        fixture.start_database()
        fixture.write_config()

        # Previous release: configure as an operator would, and issue tokens.
        # Releases with secure startup take the bootstrap file; older ones start
        # with the upstream default, which the operator changes.
        fixture.write_admin_password(admin_password)
        fixture.start(options.previous)
        fixture.ready()
        session = Session(base)
        if session.password(admin_password).get("status") != "ok":
            session = Session(base)
            session.password("123")
            session.call("/api/set-password", {"userOwner": "built-in", "userName": "admin",
                                              "oldPassword": "123", "newPassword": admin_password}, form=True)
        check("Administrator has a unique password on the previous release",
              Session(base).password(admin_password).get("status") == "ok" and Session(base).password("123").get("status") != "ok")
        fixture.remove_admin_password()
        session = admin()
        organization = session.call("/api/get-organization?id=admin/built-in")["data"]
        organization["themeData"] = THEME
        session.call("/api/update-organization?id=admin/built-in", organization)
        # Users of the built-in organization are global administrators, so the
        # client and its user live in their own organization.
        tenant = copy.deepcopy(organization)
        tenant.update(name="upgrade-org", displayName="Upgrade acceptance", themeData=None)
        org_created = session.call("/api/add-organization", tenant)
        app = copy.deepcopy(session.call("/api/get-application?id=admin/app-built-in")["data"])
        app.update(name="upgrade-app", displayName="Upgrade acceptance", clientId=client_id, clientSecret=client_secret,
                   organization="upgrade-org", cert="cert-built-in", tokenFormat="JWT", grantTypes=["password", "refresh_token"],
                   redirectUris=[base + "/callback"])
        created = session.call("/api/add-application", app)
        added = session.call("/api/add-user", {"owner": "upgrade-org", "name": "upgrade-reader", "displayName": "Upgrade reader",
                                              "password": reader_password, "type": "normal-user", "signupApplication": "upgrade-app"})
        check("State created on the previous release",
              all(r.get("status") == "ok" for r in [org_created, created, added]) and theme() == THEME,
              {"organization": org_created.get("msg"), "application": created.get("msg"), "user": added.get("msg")})
        before = issue()
        keys_before = jwks()
        check("Previous release issues verifiable tokens", active(before["access_token"]) and len(keys_before) == 1)

        # Upgrade.
        switch(options.image, "Candidate")
        check("Upgrade keeps theme and client configuration", theme() == THEME and application(admin())["clientId"] == client_id)
        check("Upgrade keeps the signing key", jwks() == keys_before)
        check("Token issued before upgrade remains active", active(before["access_token"]))
        check("Refresh token issued before upgrade still refreshes", refresh(before))
        upgraded = issue()

        # Rollback.
        switch(options.previous, "Rollback to previous release")
        check("Rollback keeps theme and signing key", theme() == THEME and jwks() == keys_before)
        check("Token issued by the candidate remains active after rollback", active(upgraded["access_token"]))
        check("Refresh token issued by the candidate refreshes after rollback", refresh(upgraded))

        # Upgrade again, then rotate the signing key with a retained previous key.
        switch(options.image, "Second upgrade")
        session = admin()
        cert = session.call("/api/add-cert", {"owner": "admin", "name": "upgrade-rotated", "displayName": "Rotated key",
                                              "scope": "JWT", "type": "x509", "cryptoAlgorithm": "RS256", "bitSize": 2048,
                                              "expireInYears": 1})
        old_token = issue()
        app = application(session)
        app["cert"] = "upgrade-rotated"
        app["retainedSigningCerts"] = [{"cert": "admin/cert-built-in", "expiresAt": int(time.time()) + 3600}]
        rotated = session.call("/api/update-application?id=admin/upgrade-app", app)
        check("Signing key rotated with the previous key retained", cert.get("status") == "ok" and rotated.get("status") == "ok")
        new_token = issue()
        check("New tokens use the rotated key", jwt_header(new_token["access_token"]).get("kid") == "upgrade-rotated"
              and jwt_header(old_token["access_token"]).get("kid") == "cert-built-in")
        check("Application JWKS publishes the rotated key", [kid for kid, _ in jwks()] == ["upgrade-rotated"])
        check("Token signed by the retained key remains active", active(old_token["access_token"]))
        check("Refresh token signed by the retained key still refreshes", refresh(old_token))
        retained_token = issue()
        app = application(session)
        app["retainedSigningCerts"] = []
        session.call("/api/update-application?id=admin/upgrade-app", app)
        check("Ending retention rejects tokens signed by the old key", not active(old_token["access_token"]))
        check("Tokens signed by the current key stay active", active(retained_token["access_token"]))

        # Backup the running database and restore it into a fresh one.
        keys_backup = jwks()
        dump = "/tmp/casdoor.dump"
        run("docker", "exec", fixture.database, "pg_dump", "-U", "postgres", "-Fc", "-f", dump, "casdoor")
        fixture.compose("stop")
        fixture.psql("CREATE DATABASE casdoor_restore OWNER casdoor", database="postgres")
        fixture.psql("REVOKE ALL ON DATABASE casdoor_restore FROM PUBLIC", database="postgres")
        run("docker", "exec", fixture.database, "pg_restore", "-U", "postgres", "--no-owner", "--role=casdoor",
            "-d", "casdoor_restore", dump)
        fixture.write_config("casdoor_restore")
        switch(options.image, "Restored backup")
        databases = fixture.psql("select distinct datname from pg_stat_activity where usename='casdoor'").stdout.split()
        check("Restored instance uses only the restored database", databases == ["casdoor_restore"])
        check("Restore keeps theme, client and signing key", theme() == THEME and application(admin())["cert"] == "upgrade-rotated"
              and jwks() == keys_backup)
        check("Token issued before the backup remains active after restore", active(retained_token["access_token"]))
        check("Refresh token issued before the backup refreshes after restore", refresh(retained_token))
    finally:
        fixture.close()
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
