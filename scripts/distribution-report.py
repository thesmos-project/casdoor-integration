#!/usr/bin/env python3
"""Check the notices and corresponding sources extracted from an actual image."""
import argparse
import hashlib
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("licenses", type=Path)
    parser.add_argument("--require-complete", action="store_true")
    parser.add_argument("--output", type=Path)
    args = parser.parse_args()
    directory = args.licenses.resolve()
    gaps, counts = [], {}
    standard_notices = json.loads((ROOT / "licenses/os-notices.json").read_text())
    for notice in standard_notices["texts"].values():
        relative = Path(notice["path"]).relative_to("licenses")
        file = directory / "third-party" / relative
        if sha256(file.read_bytes()) != notice["sha256"]:
            raise ValueError("A standard OS license text is missing or altered")
    for component, key in [("frontend", "packages"), ("backend", "modules"), ("swagger", "packages")]:
        folder = directory / "dependencies" / component
        report = json.loads((folder / "manifest.json").read_text())
        records = report[key]
        if not records:
            raise ValueError(f"Empty distribution inventory: {component}")
        counts[component] = len(records)
        if component == "frontend" and report["generated_assets_match_normal_build"] is not True:
            raise ValueError("Frontend inventory did not match the normal build")
        for item in records + [{"notices": report.get("root_notices", [])}]:
            for notice in item["notices"]:
                file = (folder / notice["path"]).resolve()
                if not file.is_relative_to(folder.resolve()) or sha256(file.read_bytes()) != notice["sha256"]:
                    raise ValueError(f"Missing, unsafe or altered notice: {component}/{notice['path']}")
            if item.get("requires_mpl_source"):
                archive = item.get("source_archive")
                if not archive:
                    raise ValueError("A covered MPL Go module has no corresponding source archive")
                file = (folder / archive["path"]).resolve()
                if not file.is_relative_to(folder.resolve()) or sha256(file.read_bytes()) != archive["sha256"]:
                    raise ValueError("MPL Go corresponding source is missing, unsafe or altered")
        gaps.extend(f"{component}: missing license text for {identity}" for identity in report["missing_license_text"])
    os_folder = directory / "dependencies/os"
    packages = []
    for paragraph in (os_folder / "installed-packages").read_text().split("\n\n"):
        metadata = dict(line.split(":", 1) for line in paragraph.splitlines() if ":" in line and len(line.split(":", 1)[0]) == 1)
        if "P" in metadata:
            packages.append({"name": metadata["P"], "version": metadata["V"], "license": metadata["L"],
                             "origin": metadata["o"], "aports_commit": metadata["c"]})
    lock = json.loads((ROOT / "os.lock.json").read_text())
    if packages != lock["packages"]:
        gaps.append("OS: installed package versions, licenses or source commits differ from os.lock.json")
    kit_folder = os_folder / "source-kit"
    if not (kit_folder / "manifest.json").is_file():
        gaps.append("OS: corresponding source kit is missing")
    else:
        kit = json.loads((kit_folder / "manifest.json").read_text())
        if kit["os_lock_sha256"] != sha256((ROOT / "os.lock.json").read_bytes()):
            raise ValueError("OS source kit does not match its lock")
        origins = {(p["origin"], p["version"], p["aports_commit"]) for p in packages}
        if origins != {(p["origin"], p["version"], p["aports_commit"]) for p in kit["origins"]}:
            raise ValueError("OS source kit does not cover the packaged binaries")
        for origin in kit["origins"]:
            if origin["source_checksums_verified_by_abuild"] is not True or not origin["files"]:
                raise ValueError("OS source checksums or recipes were not verified")
            for item in origin["files"]:
                file = (kit_folder / item["path"]).resolve()
                if not file.is_relative_to(kit_folder.resolve()) or sha256(file.read_bytes()) != item["sha256"]:
                    raise ValueError("OS corresponding source file is missing, unsafe or altered")
    counts["os_packages"] = len(packages)
    counts["mpl_go_source_archives"] = sum(m.get("requires_mpl_source", False) for m in
        json.loads((directory / "dependencies/backend/manifest.json").read_text())["modules"])
    result = {"scope": "Image notice/source coverage, not legal or production approval", "counts": counts, "gaps": gaps,
              "coverage_complete": not gaps, "image_licenses_directory": "/licenses"}
    if args.output:
        args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(json.dumps(result, indent=2))
    if args.require_complete and gaps:
        return 2
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (ValueError, KeyError, OSError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(2)
