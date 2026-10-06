#!/usr/bin/env python3
"""Fetch exact Alpine build recipes and checksum-verified corresponding sources."""
import hashlib
import json
from pathlib import Path
import re
import subprocess
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
README = (
    "Corresponding source for the Alpine packages in this image\n\n"
    "Each directory includes its exact APKBUILD, patches/configuration and verified source archives in distfiles/.\n"
    "Use the Alpine release and architecture recorded in os.lock.json. In a disposable build environment with\n"
    "abuild installed, enter the package directory, set SRCDEST to its distfiles directory, and run\n"
    "abuild verify, then abuild -r. Review APKBUILD for build dependencies and configure options.\n"
    "Source copyrights and license notices are preserved in these files and archives.\n"
)


def main():
    lock = json.loads((ROOT / "os.lock.json").read_text())
    destination = ROOT / ".local/os-source-kit"
    destination.mkdir(parents=True, exist_ok=True)
    manifest = destination / "manifest.json"
    if manifest.is_file():
        existing = json.loads(manifest.read_text())
        if existing["os_lock_sha256"] != hashlib.sha256((ROOT / "os.lock.json").read_bytes()).hexdigest():
            raise ValueError("Existing OS source kit uses a different lock; move it aside before preparing again")
        expected = {"manifest.json", "README.txt"}
        for build in existing["origins"]:
            for item in build["files"]:
                expected.add(item["path"])
                file = (destination / item["path"]).resolve()
                if not file.is_relative_to(destination.resolve()) or hashlib.sha256(file.read_bytes()).hexdigest() != item["sha256"]:
                    raise ValueError("Existing OS source kit was altered; move it aside before preparing again")
        # Abuild's generated src/ links refer to its temporary container paths.
        generated_links = []
        for file in destination.rglob("*"):
            if file.is_symlink():
                if "src" not in file.relative_to(destination).parts:
                    raise ValueError("Unexpected symbolic link in OS source kit")
                generated_links.append(file)
            elif file.is_file() and file.relative_to(destination).as_posix() not in expected:
                raise ValueError("Unexpected file in OS source kit; move it aside before preparing again")
        if generated_links:
            subprocess.run(["docker", "run", "--rm", "--entrypoint", "/bin/sh", "--volume",
                            f"{destination}:/kit:rw", lock["base_image"], "-ec", "find /kit -type l -delete"], check=True)
        (destination / "README.txt").write_text(README)
        print("Existing OS corresponding source kit checksums verified")
        return
    origins = {(p["origin"], p["aports_commit"]) for p in lock["packages"]}
    builds = []

    def download_folder(directory, origin, commit, relative):
        data = subprocess.check_output(["gh", "api", f"repos/alpinelinux/aports/contents/{relative}?ref={commit}"], text=True)
        entries = json.loads(data)
        for entry in entries:
            name = entry["name"]
            if name in {".", ".."} or "/" in name:
                raise ValueError("Unsafe source recipe path")
            file = directory / name
            if entry["type"] == "dir":
                file.mkdir(exist_ok=True)
                download_folder(file, origin, commit, entry["path"])
            elif entry["type"] == "file":
                url = entry["download_url"]
                if not url.startswith(f"https://raw.githubusercontent.com/alpinelinux/aports/{commit}/"):
                    raise ValueError("Unexpected Alpine source URL")
                with urllib.request.urlopen(url, timeout=60) as response:
                    file.write_bytes(response.read())
            else:
                raise ValueError("Review symbolic links or submodules before source distribution")

    for origin, commit in sorted(origins):
        if not re.fullmatch(r"[a-z0-9+-]+", origin) or not re.fullmatch(r"[0-9a-f]{40}", commit):
            raise ValueError("Invalid Alpine source identity")
        directory = destination / origin
        directory.mkdir(exist_ok=True)
        download_folder(directory, origin, commit, "main/" + origin)
        recipe = (directory / "APKBUILD").read_text()
        version = re.search(r"^pkgver=([^\n]+)", recipe, re.M).group(1).strip('"\'')
        revision = re.search(r"^pkgrel=([^\n]+)", recipe, re.M).group(1).strip('"\'')
        expected = {p["version"] for p in lock["packages"] if p["origin"] == origin}
        if expected != {version + "-r" + revision}:
            raise ValueError(f"Alpine source recipe version differs from packaged binary: {origin}")
        # Abuild evaluates its own pinned recipe in an isolated container. No credentials enter it.
        # SRCDEST retains the full verified source archives alongside patches/configuration.
        subprocess.run(["docker", "run", "--rm", "--entrypoint", "/bin/sh", "--workdir", "/package",
                        "--env", "SRCDEST=/package/distfiles", "--volume", f"{directory}:/package:rw",
                        lock["base_image"], "-ec", "apk add --no-cache abuild >/dev/null; abuild -F fetch; abuild -F verify; if [ -d /package/src ]; then find /package/src -type l -delete; fi"], check=True)
        for file in directory.rglob("*"):
            if file.is_symlink():
                if "src" not in file.relative_to(directory).parts:
                    raise ValueError("Unexpected symbolic link in OS source kit")
                raise ValueError("Generated source links were not removed")
        files = []
        for file in sorted(directory.rglob("*")):
            if file.is_file() and not file.is_symlink():
                files.append({"path": file.relative_to(destination).as_posix(),
                              "sha256": hashlib.sha256(file.read_bytes()).hexdigest()})
        builds.append({"origin": origin, "version": version + "-r" + revision,
                       "aports_commit": commit, "recipe": f"main/{origin}",
                       "source_checksums_verified_by_abuild": True, "files": files})
        print(f"Prepared corresponding source for {origin} {version}-r{revision}", flush=True)
    report = {"scope": "Exact Alpine recipes, patches, configuration and abuild-verified source archives",
              "os_lock_sha256": hashlib.sha256((ROOT / "os.lock.json").read_bytes()).hexdigest(), "origins": builds}
    (destination / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    (destination / "README.txt").write_text(README)


if __name__ == "__main__":
    main()
