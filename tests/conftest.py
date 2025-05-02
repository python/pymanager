import os
import pytest
import random
import re
import subprocess
import sys
import winreg

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


import manage.commands
manage.commands.WELCOME = ""


from manage.logging import LOGGER, DEBUG
LOGGER.level = DEBUG

class LogCaptureHandler(list):
    def skip_until(self, pattern, args=()):
        return ('until', pattern, args)

    def __call__(self, *cmp):
        it1 = iter(self)
        for y in cmp:
            if not isinstance(y, tuple):
                op, pat, args = None, y, []
            elif len(y) == 3:
                op, pat, args = y
            elif len(y) == 2:
                op = None
                pat, args = y

            while True:
                try:
                    x = next(it1)
                except StopIteration:
                    pytest.fail(f"Not enough elements were logged looking for {pat}")
                if op == 'until' and not re.match(pat, x[0]):
                    continue
                assert re.match(pat, x[0])
                assert tuple(x[1]) == tuple(args)
                break


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


REG_TEST_ROOT = r"Software\Python\PyManagerTesting"


class RegistryFixture:
    def __init__(self, hive, root):
        self.hive = hive
        self.root = root
        self.key = None

    def __enter__(self):
        self.key = winreg.CreateKey(self.hive, self.root)
        return self

    def __exit__(self, *exc):
        if self.key:
            self.key.Close()
            from manage.pep514utils import _reg_rmtree
            _reg_rmtree(self.hive, self.root)

    def setup(self, _subkey=None, **keys):
        if not _subkey:
            _subkey = self.key
        for k, v in keys.items():
            if isinstance(v, dict):
                with winreg.CreateKey(_subkey, k) as subkey:
                    self.setup(subkey, **v)
            elif isinstance(v, str):
                winreg.SetValueEx(_subkey, k, None, winreg.REG_SZ, v)
            elif isinstance(v, (bytes, bytearray)):
                winreg.SetValueEx(_subkey, k, None, winreg.REG_BINARY, v)
            elif isinstance(v, int):
                if v.bit_count() < 32:
                    winreg.SetValueEx(_subkey, k, None, winreg.REG_DWORD, v)
                else:
                    winreg.SetValueEx(_subkey, k, None, winreg.REG_QWORD, v)
            else:
                raise TypeError("unsupported type in registry")


@pytest.fixture(scope='function')
def registry():
    with RegistryFixture(winreg.HKEY_CURRENT_USER, REG_TEST_ROOT) as key:
        yield key
