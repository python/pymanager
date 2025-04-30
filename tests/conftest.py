import os
import pytest
import random
import re
import subprocess
import sys

from pathlib import Path

TESTS = Path(__file__).absolute().parent

import _native
if not hasattr(_native, "coinitialize"):
    import _native_test
    for k in dir(_native_test):
        if k[:1] not in ("", "_"):
            setattr(_native, k, getattr(_native_test, k))


import manage
manage.EXE_NAME = "pymanager-pytest"


from manage.logging import LOGGER, DEBUG
LOGGER.level = DEBUG

class LogCaptureHandler(list):
    def __call__(self, *cmp):
        for x, y in zip(self, cmp):
            assert re.match(y[0], x[0])
            assert x[1] == y[1]
        assert len(self) == len(cmp)

@pytest.fixture
def assert_log():
    LOGGER._list = capture = LogCaptureHandler()
    try:
        yield capture
    finally:
        LOGGER._list = None


@pytest.fixture(scope="session")
def localserver():
    from urllib.request import urlopen
    from urllib.error import URLError
    port = random.randrange(10000, 20000)
    with subprocess.Popen([sys.executable, TESTS / "localserver.py", str(port)]) as p:
        try:
            p.wait(0.1)
        except subprocess.TimeoutExpired:
            pass
        else:
            raise RuntimeError("failed to launch local server")
        host = f"http://localhost:{port}"
        with urlopen(host + "/alive"): pass
        try:
            yield host
        finally:
            try:
                p.wait(0.1)
            except subprocess.TimeoutExpired:
                try:
                    with urlopen(host + "/stop"): pass
                except URLError:
                    p.kill()
                p.wait(5)


class FakeConfig:
    def __init__(self, installs=[]):
        self.installs = list(installs)
        self.shebang_can_run_anything = True
        self.shebang_can_run_anything_silently = False

    def get_installs(self):
        return self.installs


@pytest.fixture
def fake_config():
    return FakeConfig()
