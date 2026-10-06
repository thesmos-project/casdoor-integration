#!/usr/bin/env python3
"""Recover notices for the exact unmodified Swagger UI bundles shipped upstream."""
import argparse
import base64
from concurrent.futures import ThreadPoolExecutor
import hashlib
import io
import json
from pathlib import Path
import re
import tarfile
import urllib.request


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def fetch(url):
    if not url.startswith(("https://registry.npmjs.org/", "https://registry.yarnpkg.com/", "https://raw.githubusercontent.com/swagger-api/swagger-ui/")):
        raise ValueError(f"Unreviewed download host: {url}")
    with urllib.request.urlopen(url, timeout=60) as response:
        return response.read()


def archive(url, integrity):
    data = fetch(url)
    algorithm, encoded = integrity.split("-", 1)
    if algorithm not in {"sha1", "sha256", "sha512"}:
        raise ValueError("Unsupported npm archive integrity algorithm")
    if hashlib.new(algorithm, data).digest() != base64.b64decode(encoded):
        raise ValueError(f"npm archive integrity mismatch: {url}")
    return tarfile.open(fileobj=io.BytesIO(data), mode="r:gz")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    project, source, output = args.project.resolve(), args.source.resolve(), args.output.resolve()
    lock = json.loads((project / "swagger.lock.json").read_text())
    overrides = json.loads((project / "licenses/overrides.json").read_text())
    package_lock_bytes = fetch(lock["package_lock_url"])
    if sha256(package_lock_bytes) != lock["package_lock_sha256"]:
        raise ValueError("Swagger source package lock checksum mismatch")
    package_lock = json.loads(package_lock_bytes)["packages"]
    distribution = archive(lock["tarball"], lock["integrity"])
    assets = []
    for file in sorted(source.glob("swagger-ui*")):
        original = distribution.extractfile("package/" + file.name).read()
        if file.read_bytes() != original:
            raise ValueError(f"Upstream Swagger asset differs from pinned npm release: {file.name}")
        assets.append({"path": file.name, "sha256": sha256(original)})
    output.mkdir(parents=True, exist_ok=True)
    root_notices = []
    for name in ["LICENSE", "NOTICE"]:
        data = distribution.extractfile("package/" + name).read()
        file = output / name
        file.write_bytes(data)
        root_notices.append({"path": name, "sha256": sha256(data), "source": lock["tarball"]})
    dependencies = {}
    for file in source.glob("*.js.map"):
        for module in json.loads(file.read_text())["sources"]:
            start = module.find("./node_modules/")
            if start < 0:
                continue
            parts = module[start + 2:].split("/")
            index = max(i for i, p in enumerate(parts) if p == "node_modules")
            end = index + (3 if parts[index + 1].startswith("@") else 2)
            dependency_path = "/".join(parts[:end])
            name = "/".join(parts[index + 1:end])
            metadata = package_lock[dependency_path]
            identity = name + "@" + metadata["version"]
            dependencies[identity] = (name, metadata)

    def collect(item):
        identity, (name, metadata) = item
        tar = archive(metadata["resolved"], metadata["integrity"])
        directory = output / "notices" / sha256(identity.encode())[:20]
        notices = []
        declared = None
        for member in tar:
            if not member.isfile():
                continue
            relative = Path(member.name).relative_to("package")
            if ".." in relative.parts or relative.is_absolute():
                raise ValueError("Unsafe npm archive path")
            if relative.as_posix() == "package.json":
                declared = json.load(tar.extractfile(member)).get("license")
            if re.search(r"licen[cs]e|copying|copyright|notice|patents|unlicense", relative.name, re.I):
                data = tar.extractfile(member).read()
                file = directory / relative
                file.parent.mkdir(parents=True, exist_ok=True)
                file.write_bytes(data)
                notices.append({"path": file.relative_to(output).as_posix(), "sha256": sha256(data), "source": metadata["resolved"]})
        for recovered in overrides.get("npm:" + identity, {}).get("files", []):
            data = (project / recovered["path"]).read_bytes()
            if sha256(data) != recovered["sha256"]:
                raise ValueError(f"Recovered notice checksum mismatch: {identity}")
            file = directory / "recovered" / Path(recovered["path"]).name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            notices.append({"path": file.relative_to(output).as_posix(), "sha256": sha256(data), "source": recovered["source"]})
        return {"name": name, "version": metadata["version"], "integrity": metadata["integrity"],
                "declared_license": declared, "notices": notices,
                "has_license_text": any(re.search(r"licen[cs]e|copying|unlicense", Path(n["path"]).name, re.I) for n in notices)}

    with ThreadPoolExecutor(max_workers=6) as pool:
        records = list(pool.map(collect, sorted(dependencies.items())))
    report = {"scope": "All dependency paths in the pinned Swagger UI source maps; exact source package lock and npm integrity",
              "swagger": lock, "root_notices": root_notices, "assets": assets, "packages": records,
              "missing_license_text": [f"{p['name']}@{p['version']}" for p in records if not p["has_license_text"]]}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    combined = "Swagger UI and bundled dependency notices\n\n"
    for identity, notices in [("Swagger UI", root_notices)] + [(f"{p['name']}@{p['version']}", p["notices"]) for p in records]:
        for notice in notices:
            combined += f"\n===== {identity}: {notice['path']} =====\n" + (output / notice["path"]).read_text(errors="replace") + "\n"
    # The upstream JavaScript refers to these absent files. Each contains the complete notice inventory.
    supplement = output / "supplement"
    supplement.mkdir(exist_ok=True)
    for file in source.glob("*.js"):
        if f"{file.name}.LICENSE.txt" in file.read_text(errors="replace")[:250]:
            (supplement / (file.name + ".LICENSE.txt")).write_text(combined)
    print(f"Inventoried {len(records)} Swagger packages; {len(report['missing_license_text'])} missing license texts")


if __name__ == "__main__":
    main()
