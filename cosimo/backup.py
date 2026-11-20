"""Create a private local snapshot without changing the running publisher.

Usage: python3 cosimo/backup.py [NEW_BACKUP_DIR]
Publication/slot/media state must remain unchanged across capture. A changed
state leaves an explicitly failed snapshot; it must not be used for recovery.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys


def run(args, *, data=None):
    result = subprocess.run(args, input=data, capture_output=True, timeout=120)
    if result.returncode:
        raise RuntimeError(f"{args[0]} {args[1]} failed; output suppressed to protect credentials")
    return result.stdout


def main():
    if len(sys.argv) not in (1, 2):
        raise ValueError(__doc__)
    os.umask(0o077)
    root = Path(__file__).resolve().parent.parent
    private = root / "cosimo/private"
    target = (Path(sys.argv[1]).expanduser().resolve() if len(sys.argv) == 2 else
              private / "backups" / datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ"))
    target.mkdir(parents=True, exist_ok=False, mode=0o700)
    evidence = {"status": "failed", "startedAt": datetime.datetime.now(datetime.timezone.utc).isoformat()}
    try:
        probe = (root / "cosimo/restore-probe.py").read_bytes()
        before = run(["docker", "exec", "-i", "cosimo-publishing-web-1", "python", "-"], data=probe)
        (target / "expected-state.json").write_bytes(before)
        (target / "database.dump").write_bytes(run([
            "docker", "exec", "cosimo-publishing-database-1", "pg_dump", "-U", "brightbean", "-d", "brightbean", "-Fc"]))
        (target / "media.tar.gz").write_bytes(run([
            "docker", "exec", "cosimo-publishing-web-1", "tar", "-czf", "-", "-C", "/app", "media"]))
        # Keep credentials/journals out of the image and public source tree.
        for name in ["runtime.env", "database.env", "operator.env", "api-token", "handoff-journal.json", "weekly-bundle.json", "weekly-bundle-v4.json"]:
            source = private / name
            if source.exists():
                shutil.copy2(source, target / name)
                (target / name).chmod(0o600)
        after = run(["docker", "exec", "-i", "cosimo-publishing-web-1", "python", "-"], data=probe)
        if json.loads(before) != json.loads(after):
            raise RuntimeError("Publisher changed during capture; snapshot is not verified")
        image_ids = {}
        for service in ["web", "worker", "database"]:
            image_ids[service] = run(["docker", "inspect", "--format", "{{.Image}}", f"cosimo-publishing-{service}-1"]).decode().strip()
        evidence.update({"status": "captured_not_restore_verified", "images": image_ids,
                         "stateUnchanged": True, "offMachine": False,
                         "files": {p.name: {"bytes": p.stat().st_size, "sha256": hashlib.sha256(p.read_bytes()).hexdigest()}
                                   for p in target.iterdir() if p.is_file()}})
    finally:
        evidence["finishedAt"] = datetime.datetime.now(datetime.timezone.utc).isoformat()
        (target / "manifest.json").write_text(json.dumps(evidence, indent=2) + "\n")
    print(json.dumps({"status": evidence["status"], "backup": str(target)}))


if __name__ == "__main__":
    main()
