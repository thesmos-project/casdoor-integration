#!/usr/bin/env python3
"""Resolve a repository image name against the configured registry host."""
import json
import os
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]


def resolve_image(host, image):
    if not re.fullmatch(r"[a-z0-9.-]+(?::[0-9]+)?", host):
        raise ValueError("Set REGISTRY_URL to a registry hostname, optionally with a port")
    if image.startswith(host + "/"):
        repository = image[len(host) + 1:]
    else:
        first = image.split("/", 1)[0]
        if "/" in image and ("." in first or ":" in first or first == "localhost"):
            raise ValueError("REGISTRY_IMAGE must use the configured registry host")
        repository = image
    if not re.fullmatch(r"[a-z0-9]+(?:[._-]+[a-z0-9]+)*(?:/[a-z0-9]+(?:[._-]+[a-z0-9]+)*)*", repository):
        raise ValueError("Set REGISTRY_IMAGE to an image repository name or path, without a tag")
    return host + "/" + repository


def main():
    host = os.environ.get("REGISTRY_URL", "")
    image = resolve_image(host, os.environ.get("REGISTRY_IMAGE", ""))
    public_host = os.environ.get("PUBLIC_REGISTRY_URL", "")
    public_image = resolve_image(public_host, image[len(host) + 1:]) if public_host else image
    build = json.loads((ROOT / "build.lock.json").read_text())
    source = json.loads((ROOT / "upstream.lock.json").read_text())
    values = {"image": image, "image_tag": image + ":" + build["version"],
              "public_image": public_image, "public_image_tag": public_image + ":" + build["version"],
              "version": build["version"], "upstream_commit": source["commit"], **build}
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as output:
            for name, value in values.items():
                output.write(f"{name}={value}\n")
    # Registry credentials are deliberately never read by this helper.
    print(f"Resolved image repository: {image}")
    if public_image != image:
        print(f"Resolved consumer image repository: {public_image}")


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
