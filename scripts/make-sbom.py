#!/usr/bin/env python3
"""Create an SPDX inventory that includes dependencies hidden inside browser bundles."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import urllib.parse
import uuid

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("licenses", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    folder = args.licenses / "dependencies"
    build = json.loads((ROOT / "build.lock.json").read_text())
    provenance = json.loads((args.licenses / "integration-provenance.json").read_text())
    source_lock_hash = provenance["upstream_lock_sha256"]
    if source_lock_hash != hashlib.sha256((ROOT / "upstream.lock.json").read_bytes()).hexdigest():
        raise ValueError("Image source provenance does not match the current source lock")
    packages, relationships = [], []

    def package(name, version, scope, license_value="NOASSERTION", url="NOASSERTION", purl=None):
        identity = scope + ":" + name + "@" + version
        ref = "SPDXRef-" + hashlib.sha256(identity.encode()).hexdigest()[:24]
        # Retained notices supply the evidence where metadata is absent or in a legacy format.
        if not isinstance(license_value, str) or not re.fullmatch(r"[A-Za-z0-9().+ -]+", license_value) or license_value == "Public-Domain":
            license_value = "NOASSERTION"
        item = {"SPDXID": ref, "name": name, "versionInfo": version, "downloadLocation": url,
                "filesAnalyzed": False, "licenseConcluded": "NOASSERTION", "licenseDeclared": license_value,
                "copyrightText": "NOASSERTION", "comment": scope + "; evidence accompanies the image in /licenses"}
        if purl:
            item["externalRefs"] = [{"referenceCategory": "PACKAGE-MANAGER", "referenceType": "purl", "referenceLocator": purl}]
        packages.append(item)
        relationships.append({"spdxElementId": "SPDXRef-DOCUMENT", "relationshipType": "DESCRIBES", "relatedSpdxElement": ref})
        return ref

    app = package("Casdoor with Thesmos integration patches", build["version"], "Patched upstream application", "Apache-2.0",
                  "https://github.com/thesmos-project/casdoor-integration")
    for scope in ["frontend", "swagger"]:
        report = json.loads((folder / scope / "manifest.json").read_text())
        for item in report["packages"]:
            name, version = item["name"], item["version"]
            ref = package(name, version, "Bundled " + scope + " dependency; conservative source graph",
                          item.get("declared_license"), "https://registry.npmjs.org/" + name + "/" + version,
                          "pkg:npm/" + urllib.parse.quote(name, safe="/") + "@" + version)
            relationships.append({"spdxElementId": app, "relationshipType": "DEPENDS_ON", "relatedSpdxElement": ref})
    report = json.loads((folder / "backend/manifest.json").read_text())
    for item in report["modules"]:
        if item["main"]:
            continue
        url = item["source_archive"]["source"] if item.get("source_archive") else "NOASSERTION"
        ref = package(item["module"], item["version"], "Production Go import closure or embedded standard library", url=url)
        relationships.append({"spdxElementId": app, "relationshipType": "DEPENDS_ON", "relatedSpdxElement": ref})
    package("Swagger UI", json.loads((ROOT / "swagger.lock.json").read_text())["version"], "Unmodified Swagger bundles", "Apache-2.0")
    for item in json.loads((ROOT / "os.lock.json").read_text())["packages"]:
        package(item["name"], item["version"], "Installed Alpine package", item["license"],
                "https://github.com/alpinelinux/aports/tree/" + item["aports_commit"] + "/main/" + item["origin"],
                "pkg:apk/alpine/" + item["name"] + "@" + item["version"] + "?arch=x86_64")
    result = {"spdxVersion": "SPDX-2.3", "dataLicense": "CC0-1.0", "SPDXID": "SPDXRef-DOCUMENT",
              "name": "Casdoor integration distribution inventory " + build["version"],
              "documentNamespace": "https://github.com/thesmos-project/casdoor-integration/spdx/" + str(uuid.uuid4()),
              "creationInfo": {"creators": ["Tool: casdoor-integration-make-sbom"], "created": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")},
              "comment": "Conservative inventory from exact image manifests, including browser/CSS/fonts. Go linker may omit imports. NOASSERTION is not a license grant; see retained notices and review.",
              "packages": packages, "relationships": relationships}
    args.output.write_text(json.dumps(result, indent=2) + "\n")
    print(f"Recorded {len(packages)} SPDX packages, including compiled browser dependencies")


if __name__ == "__main__":
    main()
