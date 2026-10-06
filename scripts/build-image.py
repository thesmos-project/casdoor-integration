#!/usr/bin/env python3
"""Build the candidate locally; never log in to or push to a registry."""
import argparse
import json
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tag", default="casdoor-integration:candidate")
    parser.add_argument("--reference", type=Path)
    options = parser.parse_args()
    prepare = [sys.executable, str(ROOT / "scripts/prepare-source.py")]
    if options.reference:
        prepare += ["--reference", str(options.reference)]
    subprocess.run(prepare, check=True)
    lock = json.loads((ROOT / "build.lock.json").read_text())
    upstream = json.loads((ROOT / "upstream.lock.json").read_text())
    command = ["docker", "buildx", "build", "--load", "--platform", lock["platform"], "--tag", options.tag]
    arguments = {
        "GO_IMAGE": lock["go_image"], "NODE_IMAGE": lock["node_image"],
        "RUNTIME_IMAGE": lock["runtime_image"], "YARN_VERSION": lock["yarn_version"],
        "INTEGRATION_VERSION": lock["version"], "UPSTREAM_COMMIT": upstream["commit"],
        "INTEGRATION_REVISION": subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=ROOT, text=True).strip(),
    }
    if subprocess.check_output(["git", "status", "--porcelain"], cwd=ROOT, text=True).strip():
        arguments["INTEGRATION_REVISION"] += "-dirty"
    for name, value in arguments.items():
        command += ["--build-arg", f"{name}={value}"]
    command += ["--metadata-file", str(ROOT / ".local/build-metadata.json"), str(ROOT)]
    subprocess.run(command, check=True, cwd=ROOT)


if __name__ == "__main__":
    main()
