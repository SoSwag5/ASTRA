"""Test storage is isolated before test modules import application models."""
import os
import tempfile
from pathlib import Path

_TEST_ROOT = tempfile.TemporaryDirectory(prefix='astra-tests-')
os.environ['HUNTER_DATA_DIR'] = str(Path(_TEST_ROOT.name) / 'data')
os.environ['DATABASE_URL'] = 'sqlite:///' + str(Path(_TEST_ROOT.name) / 'tests.db')
os.environ['APP_TOKEN'] = ''
os.environ['PYTHON_KEYRING_BACKEND'] = 'keyring.backends.fail.Keyring'

def pytest_sessionfinish(session, exitstatus):
    import sys
    models=sys.modules.get('backend.models')
    if models is not None:
        models.engine.dispose()
    _TEST_ROOT.cleanup()
