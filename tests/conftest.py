import sys, socket
from pathlib import Path
import pytest
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def _up(port):
    try:
        socket.create_connection(("127.0.0.1", port), timeout=0.5).close(); return True
    except OSError:
        return False

def pytest_collection_modifyitems(config, items):
    if all(_up(p) for p in (8102, 8104, 8107, 8110, 8111, 8180)):
        return
    skip = pytest.mark.skip(reason="stack not running – start it with ./run.sh up")
    for it in items:
        if "stack" in it.keywords:
            it.add_marker(skip)
