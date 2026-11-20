"""Download and verify the latest committed private remote backup.

Run with boto3 installed: python cosimo/download-backup.py CREDENTIALS_JSON NEW_DIR
Credentials use Railway's bucketName/endpoint/accessKeyId/secretAccessKey fields.
Never prints credentials, object contents or signed URLs.
"""
import hashlib
import json
import os
from pathlib import Path
import re
import sys

import boto3


def main():
    os.umask(0o077)
    credentials = json.loads(Path(sys.argv[1]).read_text())
    output = Path(sys.argv[2])
    if output.exists():
        raise ValueError('Recovery destination must be new')
    client = boto3.client('s3', endpoint_url=credentials['endpoint'],
                          aws_access_key_id=credentials['accessKeyId'],
                          aws_secret_access_key=credentials['secretAccessKey'],
                          region_name=credentials['region'])
    bucket = credentials['bucketName']
    def read(key):
        return client.get_object(Bucket=bucket, Key=key)['Body'].read()
    latest = json.loads(read('latest.json'))
    prefix = latest['prefix']
    if not re.fullmatch(r'snapshots/\d{8}T\d{6}Z/', prefix):
        raise ValueError('Unexpected backup prefix')
    raw_manifest = read(prefix + 'manifest.json')
    manifest = json.loads(raw_manifest)
    if manifest.get('status') != 'captured_not_restore_verified' or not manifest.get('offMachine'):
        raise ValueError('Remote capture did not complete')
    output.mkdir(mode=0o700, parents=True)
    for name, expected in manifest['files'].items():
        if Path(name).name != name or name in {'.', '..', 'manifest.json'}:
            raise ValueError('Unsafe backup name')
        target = output / name
        client.download_file(bucket, prefix + name, str(target))
        with target.open('rb') as source:
            checksum = hashlib.file_digest(source, 'sha256').hexdigest()
        if target.stat().st_size != expected['bytes'] or checksum != expected['sha256']:
            raise ValueError('Downloaded file differs from capture manifest')
        target.chmod(0o600)
    # A local manifest also marks completion; partial downloads cannot be restored.
    (output / 'manifest.json').write_bytes(raw_manifest)
    print(json.dumps({'status': 'download_hashes_verified', 'prefix': prefix,
                      'files': len(manifest['files']), 'destination': str(output)}))


if __name__ == '__main__':
    try:
        main()
    except Exception as error:
        print(json.dumps({'status': 'failed', 'failureType': type(error).__name__}))
        raise SystemExit(1)
