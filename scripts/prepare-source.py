#!/usr/bin/env python3
"""Export exact upstream source and apply the checked, ordered patch series."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def run(*args, cwd=None):
    return subprocess.check_output(args, cwd=cwd, text=True).strip()


def tree_hash(directory):
    digest = hashlib.sha256()
    for path in sorted(directory.rglob("*")):
        if path.is_symlink():
            raise ValueError("Source export contains an unsupported symbolic link")
        if not path.is_file() or path == directory / "integration-provenance.json":
            continue
        digest.update(path.relative_to(directory).as_posix().encode() + b"\0")
        digest.update(str(path.stat().st_mode & 0o777).encode() + b"\0")
        digest.update(hashlib.sha256(path.read_bytes()).digest())
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, help="Optional local Git object cache")
    options = parser.parse_args()
    lock_bytes = (ROOT / "upstream.lock.json").read_bytes()
    lock = json.loads(lock_bytes)
    if lock["repository"] != "https://github.com/casdoor/casdoor.git":
        raise ValueError("Unexpected upstream repository")
    if not re.fullmatch(r"[0-9a-f]{40}", lock["commit"]):
        raise ValueError("Upstream commit must be a full SHA")
    fingerprint = hashlib.sha256(lock_bytes).hexdigest()
    for patch in lock["patches"]:
        name = patch["path"]
        if not re.fullmatch(r"patches/[a-z0-9-]+\.patch", name):
            raise ValueError("Invalid patch path")
        if hashlib.sha256((ROOT / name).read_bytes()).hexdigest() != patch["sha256"]:
            raise ValueError(f"Patch checksum mismatch: {name}")
    local = ROOT / ".local"
    local.mkdir(exist_ok=True)
    destination = local / "source"
    if destination.exists():
        provenance = json.loads((destination / "integration-provenance.json").read_text())
        if provenance["upstream_lock_sha256"] != fingerprint or provenance["source_tree_sha256"] != tree_hash(destination):
            raise ValueError("Existing source differs from the checked export; move it aside before preparing again")
        print("Existing source export and patch checksums verified")
        return
    with tempfile.TemporaryDirectory(prefix="prepare-", dir=local) as scratch:
        checkout = Path(scratch) / "checkout"
        command = ["git", "clone", "--filter=blob:none", "--no-checkout"]
        if options.reference:
            command += ["--reference-if-able", str(options.reference.resolve())]
        command += [lock["repository"], str(checkout)]
        subprocess.run(command, check=True)
        run("git", "checkout", "--detach", lock["commit"], cwd=checkout)
        if run("git", "rev-parse", lock["tag"] + "^{commit}", cwd=checkout) != lock["commit"]:
            raise ValueError("Release tag does not match the pinned commit")
        for patch in lock["patches"]:
            path = str(ROOT / patch["path"])
            run("git", "apply", "--check", path, cwd=checkout)
            run("git", "apply", path, cwd=checkout)
        changed = run("git", "diff", "--name-only", cwd=checkout).splitlines()
        added = run("git", "ls-files", "--others", "--exclude-standard", cwd=checkout).splitlines()
        # Export only tracked upstream source and newly added patch files.
        # Git metadata, local credentials and build caches never enter the context.
        source = Path(scratch) / "source"
        source.mkdir()
        paths = run("git", "ls-files", cwd=checkout).splitlines() + added
        for name in paths:
            relative = Path(name)
            if relative.is_absolute() or ".." in relative.parts:
                raise ValueError("Invalid source export path")
            original = checkout / relative
            if original.is_symlink():
                raise ValueError("Source export contains an unsupported symbolic link")
            if not original.is_file():
                continue
            target = source / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(original, target)
            os.chmod(target, 0o755 if original.stat().st_mode & 0o111 else 0o644)
        provenance = {
            "upstream": lock,
            "upstream_lock_sha256": fingerprint,
            "source_tree_sha256": tree_hash(source),
            "modified_paths": sorted(set(changed + added)),
        }
        (source / "integration-provenance.json").write_text(json.dumps(provenance, indent=2) + "\n")
        source.rename(destination)
        print(f"Prepared pinned source with {len(lock['patches'])} patch layers and {len(provenance['modified_paths'])} modified files")


if __name__ == "__main__":
    main()
