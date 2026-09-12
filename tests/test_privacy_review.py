"""Privacy regression checks run in child processes with synthetic storage only."""
import os
import subprocess
import sys


def isolated(tmp_path, script):
    data=tmp_path/'data'
    env={**os.environ,'HUNTER_DATA_DIR':str(data),
         'DATABASE_URL':f'sqlite:///{data / "current.db"}','APP_TOKEN':''}
    result=subprocess.run([sys.executable,'-c',script],env=env,capture_output=True,text=True,timeout=45)
    assert result.returncode==0,result.stdout+result.stderr


def test_export_excludes_import_folders_and_sessions(tmp_path):
    isolated(tmp_path,r'''
import asyncio,io,zipfile
from backend.models import DATA,initialize
from backend.main import app
import backend.privacy as privacy
initialize()
(DATA/'master.pdf').write_bytes(b'SYNTHETIC_CV')
(DATA/'.import-synthetic').mkdir()
(DATA/'.import-synthetic'/'cv.pdf').write_bytes(b'INCOMPLETE_IMPORT')
(DATA/'browser_profiles').mkdir()
(DATA/'browser_profiles'/'session').write_bytes(b'SYNTHETIC_COOKIE')
(DATA/'hunter.db').write_bytes(b'OLD_DATABASE')
response=asyncio.run(privacy.export_data())
with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
    names=archive.namelist()
    assert 'files/master.pdf' in names and 'files/hunter.db' in names
    assert not any('.import-' in name or 'browser_profiles' in name or 'current.db' in name for name in names)
''')


def test_delete_all_removes_legacy_database_but_preserves_active_database(tmp_path):
    isolated(tmp_path,r'''
from backend.models import DATA,initialize
from backend.main import app
import backend.privacy as privacy
initialize()
privacy.delete_credential=lambda name:None
(DATA/'hunter.db').write_bytes(b'PRIVATE_OLD_DATABASE')
(DATA/'hunter.db-wal').write_bytes(b'PRIVATE_OLD_WAL')
(DATA/'master.pdf').write_bytes(b'SYNTHETIC_CV')
result=privacy.delete_data(privacy.DeleteRequest(scope='all',confirmation='DELETE ALL LOCAL DATA'))
assert result['deleted']=='all'
assert (DATA/'current.db').is_file()
assert not (DATA/'hunter.db').exists() and not (DATA/'hunter.db-wal').exists()
assert not (DATA/'master.pdf').exists()
''')


def test_unrecognized_data_root_contents_fail_before_removing_anything(tmp_path):
    isolated(tmp_path,r'''
from backend.models import DATA,initialize
from backend.main import app
import backend.privacy as privacy
initialize()
(DATA/'master.pdf').write_bytes(b'SYNTHETIC_CV')
(DATA/'family-notes.txt').write_bytes(b'UNRELATED_PERSONAL_FILE')
for operation in (privacy._export_data,lambda:privacy.delete_data(privacy.DeleteRequest(scope='cv',confirmation='DELETE CV'))):
    try: operation()
    except ValueError as error: assert 'unrecognized' in str(error)
    else: raise AssertionError('Unrecognized files were accepted')
assert (DATA/'family-notes.txt').read_bytes()==b'UNRELATED_PERSONAL_FILE'
assert (DATA/'master.pdf').read_bytes()==b'SYNTHETIC_CV'
''')


def test_export_waits_for_api_mutations_to_finish(tmp_path):
    isolated(tmp_path,r'''
import asyncio,io,zipfile
from backend.models import DATA,initialize
from backend.main import mutation_lock
import backend.privacy as privacy
initialize()
async def verify():
    async with mutation_lock:
        pending=asyncio.create_task(privacy.export_data())
        await asyncio.sleep(0)
        assert not pending.done()
        (DATA/'master.pdf').write_bytes(b'FINISHED_MUTATION')
    response=await pending
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        assert archive.read('files/master.pdf')==b'FINISHED_MUTATION'
asyncio.run(verify())
''')
