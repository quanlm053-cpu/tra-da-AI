"""Install a portable npm from the official registry, verifying its published integrity."""
import base64
import hashlib
import io
import json
from pathlib import Path
import shutil
import tarfile
import urllib.request

root = Path(__file__).resolve().parent / 'tools'
target = root / 'npm'
if not (target/'bin/npm-cli.js').exists():
    metadata = json.load(urllib.request.urlopen('https://registry.npmjs.org/npm/latest', timeout=30))
    url = metadata['dist']['tarball']
    if not url.startswith('https://registry.npmjs.org/npm/-/'):
        raise RuntimeError('Unexpected registry tarball URL')
    blob = urllib.request.urlopen(url, timeout=60).read()
    expected = metadata['dist']['integrity']
    actual = 'sha512-' + base64.b64encode(hashlib.sha512(blob).digest()).decode()
    if actual != expected:
        raise RuntimeError('npm integrity mismatch')
    target.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(blob), mode='r:gz') as archive:
        for entry in archive.getmembers():
            parts = Path(entry.name).parts
            if not parts or parts[0] != 'package' or entry.issym() or entry.islnk():
                continue
            dest = target.joinpath(*parts[1:]).resolve()
            if not dest.is_relative_to(target.resolve()):
                raise RuntimeError('Unsafe archive path')
            if entry.isdir():
                dest.mkdir(parents=True, exist_ok=True)
            elif entry.isfile():
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(archive.extractfile(entry).read())
    print('Portable npm installed:', metadata['version'])
bindir = root/'bin'
bindir.mkdir(parents=True,exist_ok=True)
node = shutil.which('node')
for command, entry in [('npm','npm-cli.js'),('npx','npx-cli.js')]:
    (bindir/(command+'.cmd')).write_text(f'@echo off\r\n"{node}" "{target/"bin"/entry}" %*\r\n',encoding='utf-8')
print('Portable tools ready:',bindir)
