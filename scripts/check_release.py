"""Verify every ZIP member, then start the extracted code against its own data."""
from pathlib import Path
import hashlib
import json
import subprocess
import sys
import time
import zipfile
import argparse

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from mom_basis.model import VERSION
parser=argparse.ArgumentParser(description=__doc__)
parser.add_argument('--archive',type=Path,default=ROOT.parent/f'Signal_GFIVIP_4h_MVP_v{VERSION}.zip')
parser.add_argument('--report',type=Path)
args=parser.parse_args();archive=args.archive
destination=ROOT.parent/('gfi_release_check_'+str(int(time.time())))
destination.mkdir()
with zipfile.ZipFile(archive) as z:
    for name in z.namelist():
        assert (destination/name).resolve().is_relative_to(destination.resolve())
    z.extractall(destination)
release=destination/'Signal_GFIVIP_4h_MVP'
manifest=json.loads((release/'MANIFEST_SHA256.json').read_text(encoding='utf-8'))
for name,digest in manifest.items():
    assert hashlib.sha256((release/name).read_bytes()).hexdigest()==digest,name
command=[sys.executable,'-m','mom_basis','replay','--out',str(destination/'verification')]
replay=subprocess.run(command,cwd=release,text=True,capture_output=True,check=True)
api_code="""
from fastapi.testclient import TestClient
from mom_basis.api import create_app
app=create_app('.release_state',live=False)
with TestClient(app) as c:
    import json,pathlib
    expected=json.loads(pathlib.Path('evidence/continuous/summary.json').read_text(encoding='utf-8'))
    stats=c.get('/api/stats').json()
    assert stats['n_trades']==expected['n_trades']
    assert abs(stats['net_profit']-expected['net_profit'])<1e-10
    assert stats['data_as_of_ms']==expected['data_as_of_ms']
    assert stats['signal_name']=='Signal_GFIVIP_4h'
    assert len(c.get('/api/notifications').json()['items'])==5
    assert 'Signal_GFIVIP_4h' in c.get('/').text
    assert c.get('/assets/app.js').status_code==200
print('Extracted API and UI assets OK')
"""
api=subprocess.run([sys.executable,'-c',api_code],cwd=release,text=True,capture_output=True,check=True)
result=dict(manifest_members_verified=len(manifest),standalone_extracted_replay=True,
            standalone_api=True,standalone_ui_assets=True,
            archive_contains_runtime_state=False,extracted_to=str(release),
            replay_stdout=replay.stdout.strip(),api_stdout=api.stdout.strip())
(args.report or archive.with_suffix('.verification.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
print(json.dumps(result))
