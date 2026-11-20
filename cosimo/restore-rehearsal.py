"""Restore an existing private snapshot into disposable, network-isolated Docker.

Usage: python3 cosimo/restore-rehearsal.py BACKUP_DIR NEW_EVIDENCE_DIR
Never starts a web server, worker, migrations, or platform provider.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tarfile
import time
import uuid


def run(args, *, data=None, timeout=120):
    proc = subprocess.run(args, input=data, stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout)
    if proc.returncode:
        # Runtime configuration and database values must never leak in diagnostics.
        failure = RuntimeError(f"Command failed: {args[0]} {args[1]} (exit {proc.returncode}; stderr suppressed)")
        failure.private_stderr = proc.stderr
        failure.command_kind = args[:2]
        raise failure
    return proc.stdout


def sha(path):
    h = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            h.update(part)
    return h.hexdigest()


def archive_members(path):
    with tarfile.open(path, "r:gz") as archive:
        members = archive.getmembers()
        seen = set()
        for member in members:
            name = Path(member.name)
            if name.is_absolute() or ".." in name.parts or not name.parts or name.parts[0] != "media":
                raise ValueError("Unsafe media archive path")
            if not (member.isdir() or member.isfile()) or member.name in seen:
                raise ValueError("Unsafe or repeated media archive entry")
            seen.add(member.name)
        return members


def main():
    if len(sys.argv) != 3:
        raise ValueError(__doc__)
    backup, output = (Path(p).expanduser().resolve() for p in sys.argv[1:])
    required = ["database.dump", "media.tar.gz", "runtime.env", "database.env", "handoff-journal.json"]
    for name in required:
        if not (backup / name).is_file():
            raise ValueError(f"Missing backup file: {name}")
    if not (backup / "expected-state.json").is_file() and not (backup / "weekly-bundle.json").is_file():
        raise ValueError("Snapshot needs expected-state.json or legacy weekly-bundle.json")
    saved_manifest = backup / "manifest.json"
    postgres_image = "postgres:16-alpine"
    if saved_manifest.exists():
        captured = json.loads(saved_manifest.read_text())
        if captured.get("status") != "captured_not_restore_verified":
            raise ValueError("Backup capture did not complete")
        for name, expected in captured["files"].items():
            if Path(name).name != name or not (backup / name).is_file() or sha(backup / name) != expected["sha256"]:
                raise ValueError("Backup file differs from capture manifest")
        postgres_image = captured.get("postgresImage", postgres_image)
        if postgres_image not in {"postgres:16-alpine", "postgres:18-alpine"}:
            raise ValueError("Unsupported PostgreSQL recovery image")
    if output.exists():
        raise ValueError("Evidence destination must not already exist")
    members = archive_members(backup / "media.tar.gz")
    os.umask(0o077)
    output.mkdir(parents=True, mode=0o700)
    private = output / "restored-files"
    private.mkdir(mode=0o700)
    manifest = {p.name: {"bytes": p.stat().st_size, "sha256": sha(p)} for p in backup.iterdir() if p.is_file()}
    probe = Path(__file__).with_name("restore-probe.py").read_bytes()
    probe_path = output / "probe.py"
    probe_path.write_bytes(probe)
    web = "cosimo-publishing-web-1"
    image = run(["docker", "inspect", "--format", "{{.Image}}", web]).decode().strip()
    before = json.loads(run(["docker", "exec", "-i", web, "python", "-"], data=probe))
    db = "cosimo-restore-" + uuid.uuid4().hex[:12]
    app = db + "-probe"
    evidence = {"schemaVersion": 1, "startedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                "backup": str(backup), "backupManifest": manifest, "appImageId": image,
                "status": "failed", "networkMode": "none", "workerStarted": False, "productionWrites": 0}
    try:
        with tarfile.open(backup / "media.tar.gz", "r:gz") as archive:
            for member in members:
                target = private / member.name
                if member.isdir():
                    target.mkdir(parents=True, exist_ok=True, mode=0o700)
                else:
                    target.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
                    with archive.extractfile(member) as source, target.open("xb") as dest:
                        shutil.copyfileobj(source, dest)
        run(["docker", "run", "-d", "--name", db, "--network", "none", "--restart", "no",
             "-e", "POSTGRES_HOST_AUTH_METHOD=trust", "-e", "POSTGRES_USER=restore", "-e", "POSTGRES_DB=restore",
             postgres_image])
        for attempt in range(40):
            # The image starts a temporary socket-only server during initdb.
            # Wait for TCP so that temporary readiness cannot start pg_restore
            # immediately before the initialization server shuts down.
            ready = subprocess.run(["docker", "exec", db, "pg_isready", "-h", "127.0.0.1", "-U", "restore", "-d", "restore"], capture_output=True)
            if ready.returncode == 0:
                break
            time.sleep(0.5)
        else:
            raise RuntimeError("Disposable PostgreSQL did not become ready")
        run(["docker", "exec", "-i", db, "pg_restore", "-U", "restore", "-d", "restore", "--no-owner", "--no-acl", "--exit-on-error"], data=(backup / "database.dump").read_bytes())
        restored = json.loads(run([
            "docker", "run", "--rm", "--name", app, "--network", "container:" + db,
            "--env-file", str(backup / "runtime.env"),
            "-e", "DATABASE_URL=postgres://restore@127.0.0.1:5432/restore",
            "-e", "COSIMO_RESTORE_PROBE=1", "-e", "STORAGE_BACKEND=local", "-e", "MEDIA_ROOT=/restore-media",
            "-v", str(backup) + ":/backup:ro", "-v", str(private / "media") + ":/restore-media:ro",
            "-v", str(probe_path) + ":/restore-probe.py:ro", image, "python", "/restore-probe.py"]))
        # Compare restored records with their captured snapshot inside the probe.
        # Live records may legitimately have changed since a historical backup.
        evidence["restored"] = restored
    except BaseException as exc:
        evidence["failureType"] = type(exc).__name__
        if hasattr(exc, "private_stderr"):
            (output / "failure-stderr.txt").write_bytes(exc.private_stderr)
            evidence["failedCommand"] = exc.command_kind
    finally:
        errors = []
        # docker run may create a container before returning an error/timeout.
        # Always attempt both uniquely named resources, even after partial start.
        for container in [app, db]:
            try:
                subprocess.run(["docker", "rm", "-f", "-v", container], capture_output=True, timeout=30)
            except Exception as exc:
                errors.append({"check": "cleanup", "failureType": type(exc).__name__})
        checks = {
            "productionStateUnchanged": lambda: before == json.loads(run(["docker", "exec", "-i", web, "python", "-"], data=probe)),
            "backupFilesUnchanged": lambda: all(sha(backup / name) == item["sha256"] for name, item in manifest.items()),
            "disposableContainersRemoved": lambda: not run(["docker", "ps", "-a", "--filter", "name=" + db, "--format", "{{.Names}}"]).strip(),
        }
        for name, check in checks.items():
            try:
                evidence[name] = check()
            except Exception as exc:
                evidence[name] = None
                errors.append({"check": name, "failureType": type(exc).__name__})
        evidence["finalizationErrors"] = errors
        passed = not errors and not evidence.get("failureType") and "restored" in evidence and all(evidence[name] is True for name in checks)
        evidence["status"] = "verified" if passed else "failed"
        evidence["completedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (output / "verification.json").write_text(json.dumps(evidence, indent=2) + "\n")
    if evidence["status"] != "verified":
        raise RuntimeError(f"Restore rehearsal failed; inspect private evidence at {output / 'verification.json'}")
    print(json.dumps({"status": evidence["status"], "evidence": str(output / "verification.json"),
                      "tables": len(evidence["restored"]["tableCounts"]), "mediaFiles": len(evidence["restored"]["mediaFiles"])}))


if __name__ == "__main__":
    main()
