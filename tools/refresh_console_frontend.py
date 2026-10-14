#!/usr/bin/env python3
"""Freeze the existing frontend bytes; source changes require an explicit refresh."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import tarfile

ROOT = Path(__file__).resolve().parents[1]


def refresh():
    files = {p.relative_to(ROOT / 'console/dist').as_posix(): p.read_bytes()
             for p in (ROOT / 'console/dist').rglob('*') if p.is_file()}
    if 'index.html' not in files:
        raise ValueError('Build the frontend before refreshing its input archive')
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode='w', format=tarfile.USTAR_FORMAT) as archive:
        for name, raw in sorted(files.items()):
            entry = tarfile.TarInfo(name); entry.size = len(raw); entry.mode = 0o444; entry.mtime = 0
            archive.addfile(entry, io.BytesIO(raw))
    raw = gzip.compress(buf.getvalue(), mtime=0)
    target = ROOT / 'console/frontend.tar.gz'; target.write_bytes(raw)
    sources = [ROOT / 'console' / name for name in ('package.json', 'package-lock.json', 'index.html',
               'vite.config.ts', 'tsconfig.json')] + sorted((ROOT / 'console/src').rglob('*'))
    lock = dict(archiveSHA256=hashlib.sha256(raw).hexdigest(),
                filesSHA256={name: hashlib.sha256(value).hexdigest() for name, value in files.items()},
                sourcesSHA256={p.relative_to(ROOT).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
                               for p in sources if p.is_file()})
    (ROOT / 'console/frontend.lock.json').write_text(json.dumps(lock, indent=2) + '\n', encoding='utf-8', newline='\n')


if __name__ == '__main__':
    refresh()
