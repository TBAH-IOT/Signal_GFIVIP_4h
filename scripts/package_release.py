"""Build a source ZIP with data and evidence, excluding runtime state and credentials."""
from pathlib import Path
import hashlib
import json
import zipfile

ROOT=Path(__file__).resolve().parents[1]
DEST=ROOT.parent/'Signal_GFIVIP_4h_MVP_v1.1.0.zip'
allowed_dirs={'mom_basis','web','tests','scripts','docs','data','evidence'}
allowed_files={'README.md','pyproject.toml','requirements.lock','requirements-test.lock',
               'install.ps1','start_offline.ps1','start_live.ps1','Dockerfile','compose.yaml','.dockerignore','.gitignore'}
files=[p for p in ROOT.rglob('*') if p.is_file() and
       not any(part.startswith('.') or part=='__pycache__' for part in p.relative_to(ROOT).parts[:-1]) and
       (p.relative_to(ROOT).parts[0] in allowed_dirs or str(p.relative_to(ROOT)) in allowed_files) and
       p.suffix not in {'.pyc','.sqlite3','.key'}]
manifest={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(files)}
(ROOT/'MANIFEST_SHA256.json').write_text(json.dumps(manifest,indent=2),encoding='utf-8')
files.append(ROOT/'MANIFEST_SHA256.json')
with zipfile.ZipFile(DEST,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
    for p in files:
        z.write(p,arcname='Signal_GFIVIP_4h_MVP/'+p.relative_to(ROOT).as_posix())
with zipfile.ZipFile(DEST) as z:
    assert z.testzip() is None
    assert all('.venv/' not in n and '.key' not in n and '.sqlite3' not in n for n in z.namelist())
sha=hashlib.sha256(DEST.read_bytes()).hexdigest()
DEST.with_suffix('.zip.sha256').write_text(sha+'  '+DEST.name+'\n',encoding='ascii')
print(json.dumps(dict(zip=str(DEST),bytes=DEST.stat().st_size,files=len(files),sha256=sha)))
