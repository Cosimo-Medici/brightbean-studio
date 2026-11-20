"""Daily Railway backup to a separate private bucket. Never starts a publisher.

Uploads a complete manifest last; latest.json only advances after all uploads.
Read back and restore the actual destination separately to establish recovery.
"""
import datetime
import hashlib
import json
import os
from pathlib import Path
import subprocess
import tarfile
import tempfile

import boto3
from psycopg.conninfo import conninfo_to_dict


def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def client(prefix):
    return boto3.client('s3', endpoint_url=os.environ[prefix + 'ENDPOINT_URL'],
                        aws_access_key_id=os.environ[prefix + 'ACCESS_KEY_ID'],
                        aws_secret_access_key=os.environ[prefix + 'SECRET_ACCESS_KEY'],
                        region_name=os.environ.get(prefix + 'REGION_NAME', 'auto'))


def probe():
    result = subprocess.run(['python', 'cosimo/restore-probe.py'], capture_output=True, timeout=300)
    if result.returncode:
        # Report only a Python exception class and source location, never the
        # exception message, connection string or environment values.
        import re
        lines = result.stderr.decode(errors='replace').splitlines()
        kind = lines[-1].split(':', 1)[0] if lines else 'Unknown'
        frames = re.findall(r'File "([^"\n]+)", line (\d+)', '\n'.join(lines))
        safe = {'stage': 'snapshot_probe', 'exitCode': result.returncode}
        if re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*', kind):
            safe['failureType'] = kind
        if frames:
            safe['sourceFile'], safe['sourceLine'] = frames[-1]
        print(json.dumps(safe), flush=True)
        raise RuntimeError('Snapshot probe failed; diagnostic values suppressed')
    return json.loads(result.stdout)


def main():
    os.umask(0o077)
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    prefix = 'snapshots/' + stamp + '/'
    media, backup = client('S3_'), client('BACKUP_S3_')
    bucket = os.environ['BACKUP_S3_BUCKET_NAME']
    with tempfile.TemporaryDirectory() as tmp:
        root = Path(tmp)
        before = probe()
        (root / 'expected-state.json').write_text(json.dumps(before, indent=2) + '\n')
        # PGDATABASE is a database name, not a place to smuggle a connection URI.
        # Keep credentials out of argv and pass parsed libpq fields explicitly.
        connection = conninfo_to_dict(os.environ['DATABASE_URL'])
        libpq = {'dbname': 'PGDATABASE', 'host': 'PGHOST', 'port': 'PGPORT',
                 'user': 'PGUSER', 'password': 'PGPASSWORD', 'sslmode': 'PGSSLMODE',
                 'sslrootcert': 'PGSSLROOTCERT', 'connect_timeout': 'PGCONNECT_TIMEOUT',
                 'options': 'PGOPTIONS', 'application_name': 'PGAPPNAME'}
        unknown = set(connection) - set(libpq)
        if unknown:
            raise ValueError('Unsupported libpq recovery connection option')
        dump_env = dict(os.environ)
        dump_env.update({libpq[key]: value for key, value in connection.items()})
        result = subprocess.run(['pg_dump', '-Fc', '--file', str(root / 'database.dump')],
                                env=dump_env, capture_output=True, timeout=300)
        if result.returncode:
            diagnostic = result.stderr.decode(errors='replace').lower()
            known = ['server version', 'connection', 'permission denied',
                     'could not translate', 'timeout', 'does not exist', 'aborting']
            print(json.dumps({'stage': 'database_export', 'exitCode': result.returncode,
                              'failureHints': [hint for hint in known if hint in diagnostic]}), flush=True)
            raise RuntimeError('Database export failed; connection details suppressed')
        seen = set()
        with tarfile.open(root / 'media.tar.gz', 'w:gz') as archive:
            for item in before['mediaFiles']:
                name = item['path']
                path = Path(name)
                if path.is_absolute() or '..' in path.parts:
                    raise ValueError('Unsafe stored media name')
                if name in seen:
                    continue
                seen.add(name)
                local = root / 'object.tmp'
                media.download_file(os.environ['S3_BUCKET_NAME'], name, str(local))
                if local.stat().st_size != item['bytes'] or digest(local) != item['sha256']:
                    raise RuntimeError('Media changed during capture')
                archive.add(local, arcname='media/' + name, recursive=False)
                local.unlink()
        keys = json.loads(os.environ['RECOVERY_RUNTIME_KEYS'])
        runtime = {key: os.environ[key] for key in keys}
        if any('\n' in value or '\r' in value for value in runtime.values()):
            raise ValueError('Multiline configuration needs an explicit recovery format')
        (root / 'runtime.env').write_text(''.join(k + '=' + v + '\n' for k, v in runtime.items()))
        # The isolated recovery tool supplies its own role/database. Preserve
        # production connection configuration in runtime.env, never in logs.
        (root / 'database.env').write_text('POSTGRES_USER=restore\nPOSTGRES_DB=restore\n')
        recovery = json.loads(os.environ['RECOVERY_FILES_JSON'])
        allowed = {'handoff-journal.json', 'operator.env', 'api-token'}
        if not set(recovery).issubset(allowed) or 'handoff-journal.json' not in recovery:
            raise ValueError('Invalid recovery file set')
        for name, value in recovery.items():
            (root / name).write_text(value)
        if before != probe():
            raise RuntimeError('Publishing state changed during capture; retry the next run')
        manifest = {'status': 'captured_not_restore_verified', 'offMachine': True,
                    'capturedAt': stamp, 'postgresImage': 'postgres:18-alpine',
                    'stateUnchanged': True,
                    'files': {p.name: {'bytes': p.stat().st_size, 'sha256': digest(p)}
                              for p in root.iterdir() if p.is_file()}}
        # A manifest is the commit marker. Partial prefixes are never selected.
        for name in manifest['files']:
            backup.upload_file(str(root / name), bucket, prefix + name)
        backup.put_object(Bucket=bucket, Key=prefix + 'manifest.json',
                          Body=json.dumps(manifest, indent=2).encode(), ContentType='application/json')
        backup.put_object(Bucket=bucket, Key='latest.json',
                          Body=json.dumps({'prefix': prefix, 'capturedAt': stamp}).encode(),
                          ContentType='application/json')
        print(json.dumps({'status': manifest['status'], 'prefix': prefix,
                          'files': len(manifest['files']), 'mediaFiles': len(seen), 'offMachine': True}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        # Provider/DB exceptions can contain connection strings or signed URLs.
        safe_messages = {'Snapshot probe failed; diagnostic values suppressed',
                         'Database export failed; connection details suppressed',
                         'Media changed during capture',
                         'Publishing state changed during capture; retry the next run'}
        failure = {'status': 'failed', 'failureType': type(error).__name__}
        if str(error) in safe_messages:
            failure['reason'] = str(error)
        print(json.dumps(failure))
        raise SystemExit(1)
