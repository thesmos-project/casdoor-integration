#!/usr/bin/env python3
"""Run the Compose recipe against a disposable TLS PostgreSQL database.

Checks secure startup, administrator TOTP MFA and recovery, restart persistence,
sign-in lockout and verified TLS to the database. Everything runs on loopback
and is removed afterwards; the report contains no passwords, secrets or tokens.
"""
import argparse
import json
from pathlib import Path
import secrets

from acceptance_fixture import ROOT, RecipeFixture, Session, totp, wait_for_next_totp_window


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--image", default="casdoor-integration:candidate")
    parser.add_argument("--output", type=Path, default=ROOT / ".local/recipe-acceptance.json")
    options = parser.parse_args()
    report = {"image": options.image, "scope": "Disposable loopback recipe acceptance; not a capacity or HTTPS test", "checks": {}}
    fixture = RecipeFixture(options.image)

    def check(name, passed):
        report["checks"][name] = bool(passed)
        print(("PASS " if passed else "FAIL ") + name)
        if not passed:
            raise RuntimeError(name)

    try:
        fixture.start_database()
        fixture.write_config()
        fixture.start()
        fixture.wait_exited()
        check("Fresh database without bootstrap secret refuses to start", "Secure startup refused" in fixture.logs())

        admin_password = secrets.token_urlsafe(24)
        fixture.write_admin_password(admin_password)
        fixture.start()
        fixture.ready()
        base = fixture.base
        check("Upstream default administrator password rejected", Session(base).password("123").get("status") != "ok")
        admin = Session(base)
        check("Bootstrap administrator password signs in", admin.password(admin_password).get("status") == "ok")
        connections, encrypted = fixture.psql(
            "select count(*), bool_and(s.ssl) from pg_stat_ssl s join pg_stat_activity a using (pid) where a.usename='casdoor'").stdout.strip().split("|")
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
        fixture.write_admin_password(replacement)
        if fixture.compose("restart").returncode != 0:
            raise RuntimeError("restart failed")
        fixture.ready()
        check("Restart with a changed secret file keeps the administrator password", Session(base).password(replacement).get("status") != "ok")
        check("MFA remains required after restart", Session(base).password(admin_password).get("data") == "NextMfa")
        # Casdoor's default abuse control: five wrong passwords freeze sign-in for 15 minutes.
        for _ in range(5):
            Session(base).password(secrets.token_urlsafe(12))
        check("Repeated wrong passwords freeze administrator sign-in", Session(base).password(admin_password).get("status") != "ok")
    finally:
        fixture.close()
        options.output.parent.mkdir(parents=True, exist_ok=True)
        options.output.write_text(json.dumps(report, indent=2) + "\n")
    print(json.dumps(report))


if __name__ == "__main__":
    main()
