#!/usr/bin/env python3
"""Validate build inputs and fail closed when registry publication is unapproved."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
GATES = {
    "security_review", "dependency_and_asset_licensing", "bootstrap_mfa_and_recovery",
    "protocol_and_upgrade_acceptance", "deployment_and_capacity_acceptance", "independent_review",
}


def build_inputs_hash():
    digest = hashlib.sha256()
    inputs = [ROOT / "upstream.lock.json", ROOT / "build.lock.json", ROOT / "Dockerfile", ROOT / ".dockerignore"]
    inputs += sorted((ROOT / "scripts").glob("*.py"))
    inputs += sorted((ROOT / "docker").glob("*"))
    inputs += sorted((ROOT / "licenses").glob("*"))
    inputs += sorted((ROOT / ".github/workflows").glob("*.yml"))
    inputs += [ROOT / "LICENSE", ROOT / "NOTICE"]
    for path in sorted(inputs):
        digest.update(path.relative_to(ROOT).as_posix().encode() + b"\0" + path.read_bytes())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--release", action="store_true")
    parser.add_argument("--print-inputs-sha256", action="store_true")
    options = parser.parse_args()
    source = json.loads((ROOT / "upstream.lock.json").read_text())
    build = json.loads((ROOT / "build.lock.json").read_text())
    if source["repository"] != "https://github.com/casdoor/casdoor.git" or not re.fullmatch(r"[0-9a-f]{40}", source["commit"]):
        raise ValueError("Invalid upstream identity")
    if not source["patches"]:
        raise ValueError("Missing patch series")
    seen = set()
    for patch in source["patches"]:
        path = patch["path"]
        if not re.fullmatch(r"patches/[a-z0-9-]+\.patch", path) or path in seen:
            raise ValueError("Invalid or repeated patch path")
        seen.add(path)
        if hashlib.sha256((ROOT / path).read_bytes()).hexdigest() != patch["sha256"]:
            raise ValueError(f"Patch checksum mismatch: {path}")
    if seen != {p.relative_to(ROOT).as_posix() for p in (ROOT / "patches").glob("*.patch")}:
        raise ValueError("The patch directory and lock must contain the same series")
    if build["platform"] != "linux/amd64":
        raise ValueError("Only linux/amd64 is currently supported")
    dockerfile = (ROOT / "Dockerfile").read_text()
    for key, argument in [("go_image", "GO_IMAGE"), ("node_image", "NODE_IMAGE"), ("runtime_image", "RUNTIME_IMAGE")]:
        if not re.fullmatch(r"[a-z0-9./:-]+@sha256:[0-9a-f]{64}", build[key]):
            raise ValueError(f"Image must be pinned by digest: {key}")
        if f"ARG {argument}={build[key]}\n" not in dockerfile:
            raise ValueError(f"Dockerfile and build lock disagree: {key}")
    if not re.fullmatch(r"v[0-9]+\.[0-9]+\.[0-9]+-thesmos\.[0-9]+(?:-rc\.[0-9]+)?", build["version"]):
        raise ValueError("Invalid integration version")
    policy = json.loads((ROOT / "release-policy.json").read_text())
    if set(policy["required_acceptance"]) != GATES:
        raise ValueError("Release policy must retain every required acceptance gate")
    if options.print_inputs_sha256:
        print(build_inputs_hash())
        return
    if options.release:
        if policy["production_ready"] is not True or policy["registry_publication_approved"] is not True:
            raise ValueError("Registry publishing is blocked: production and publication acceptance are pending")
        if any(value is not True for value in policy["required_acceptance"].values()):
            raise ValueError("Registry publishing is blocked: an acceptance gate remains open")
        # Acceptance evidence must bind to the exact candidate inputs, not a prior build.
        if policy.get("accepted_build_inputs_sha256") != build_inputs_hash():
            raise ValueError("Registry publishing is blocked: acceptance does not match current build inputs")
        if not policy.get("acceptance_evidence") or not policy.get("reviewed_by"):
            raise ValueError("Registry publishing is blocked: acceptance evidence and reviewer are required")
    print(f"Validated {len(source['patches'])} pinned patches and build inputs" + (" for release" if options.release else "; production approval remains separate"))


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
