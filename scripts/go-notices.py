#!/usr/bin/env python3
"""Record production Go imports and retain module/toolchain notice texts."""
import argparse
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess


def sha256(data):
    return hashlib.sha256(data).hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("project", type=Path)
    args = parser.parse_args()
    source, output, project = args.source.resolve(), args.output.resolve(), args.project.resolve()
    overrides = json.loads((project / "licenses/overrides.json").read_text())
    raw = subprocess.check_output(["go", "list", "-mod=readonly", "-deps", "-json", "."], cwd=source, text=True)
    decoder = json.JSONDecoder()
    modules, imports = {}, []
    while raw.strip():
        item, end = decoder.raw_decode(raw.lstrip())
        raw = raw.lstrip()[end:]
        if item.get("Error") or item.get("DepsErrors"):
            raise ValueError("Go import closure contains errors")
        imports.append(item["ImportPath"])
        module = item.get("Module")
        if module:
            if module.get("Replace"):
                raise ValueError("Review module replacements before distribution")
            modules[module["Path"]] = module
    goroot = subprocess.check_output(["go", "env", "GOROOT"], text=True).strip()
    version = subprocess.check_output(["go", "env", "GOVERSION"], text=True).strip()
    modules["Go toolchain"] = {"Path": "Go toolchain", "Version": version, "Dir": goroot}
    records = []
    output.mkdir(parents=True, exist_ok=True)
    for name, module in sorted(modules.items()):
        folder = Path(module["Dir"])
        identity = f"{name}@{module.get('Version', 'source')}"
        target = output / "notices" / sha256(identity.encode())[:20]
        notices = []

        def copy(relative, data, origin, license_text=False):
            file = target / relative
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_bytes(data)
            notices.append({"path": file.relative_to(output).as_posix(), "sha256": sha256(data), "source": origin,
                            "license_text": license_text or bool(re.search(r"licen[cs]e|copying|unlicense", file.name, re.I))})

        # Include nested/vendor notices as well as root license and patent grants.
        for file in sorted(folder.rglob("*")):
            if not file.is_file() or file.is_symlink():
                continue
            if re.search(r"licen[cs]e|copying|copyright|notice|patents|unlicense", file.name, re.I) or any(
                    re.fullmatch(r"licen[cs]es?", part, re.I) for part in file.relative_to(folder).parts[:-1]):
                copy(file.relative_to(folder), file.read_bytes(), "Pinned Go module or toolchain source")
        for replacement in overrides.get(f"go:{identity}", {}).get("files", []):
            data = (project / replacement["path"]).read_bytes()
            if sha256(data) != replacement["sha256"]:
                raise ValueError(f"Recovered notice checksum mismatch: {identity}")
            copy(Path("recovered") / Path(replacement["path"]).name, data, replacement["source"], replacement.get("license_text", False))
        # A copyright prefix or a vendor notice must not hide a covered component.
        mpl = any(re.search(r"Mozilla Public License[^\n]*2\.0", (output / n["path"]).read_text(errors="replace"), re.I) for n in notices)
        source_archive = None
        if mpl and not module.get("Main") and name != "Go toolchain":
            downloaded = json.loads(subprocess.check_output(["go", "mod", "download", "-json", name + "@" + module["Version"]], cwd=source, text=True))
            archive = output / "sources" / (sha256(identity.encode())[:20] + ".zip")
            archive.parent.mkdir(exist_ok=True)
            shutil.copyfile(downloaded["Zip"], archive)
            source_archive = {"path": archive.relative_to(output).as_posix(), "sha256": sha256(archive.read_bytes()),
                              "go_module_sum": downloaded["Sum"], "source": "https://proxy.golang.org/" + name + "/@v/" + module["Version"] + ".zip"}
        records.append({"module": name, "version": module.get("Version"), "main": bool(module.get("Main")),
                        "notices": notices, "has_license_text": any(n["license_text"] for n in notices),
                        "requires_mpl_source": mpl, "source_archive": source_archive})
    report = {"scope": "Production Go import closure and toolchain; conservative nested notice inventory",
              "go_version": version, "import_count": len(imports), "imports": sorted(imports), "modules": records,
              "go_sum_sha256": sha256((source / "go.sum").read_bytes()),
              "missing_license_text": [f"{m['module']}@{m['version']}" for m in records if not m["has_license_text"]]}
    (output / "manifest.json").write_text(json.dumps(report, indent=2) + "\n")
    print(f"Inventoried {len(records)} Go modules/toolchain; {len(report['missing_license_text'])} missing license texts")


if __name__ == "__main__":
    main()
