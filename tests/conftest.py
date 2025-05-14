import os
import pytest
import random
import re
import subprocess
import sys
import winreg

from pathlib import Path, PurePath

TESTS = Path(__file__).absolute().parent

import _native
if not hasattr(_native, "coinitialize"):
    import _native_test
    for k in dir(_native_test):
        if k[:1] not in ("", "_"):
            setattr(_native, k, getattr(_native_test, k))


# Importing in order carefully to ensure the variables we override are handled
# correctly by submodules.
import manage
manage.EXE_NAME = "pymanager-pytest"

import manage.commands
manage.commands.WELCOME = ""

from manage.logging import LOGGER, DEBUG, ERROR
LOGGER.level = DEBUG

import manage.config
import manage.installs


# Ensure we don't pick up any settings from configs or the registry

def _mock_load_global_config(cfg, schema):
    cfg.update({
        "base_config": "",
        "user_config": "",
        "additional_config": "",
    })

def _mock_load_registry_config(key, schema):
    return {}

manage.config.load_global_config = _mock_load_global_config
manage.config.load_registry_config = _mock_load_registry_config


@pytest.fixture
def quiet_log():
    lvl = LOGGER.level
    LOGGER.level = ERROR
    try:
        yield
    finally:
        LOGGER.level = lvl


class LogCaptureHandler(list):
    def skip_until(self, pattern, args=None):
        return ('until', pattern, args)

    def not_logged(self, pattern, args=None):
        return ('not', pattern, args)

    def end_of_log(self):
        return ('eol', None, None)

    def __call__(self, *cmp):
        i = 0
        for y in cmp:
            if not isinstance(y, tuple):
                op, pat, args = None, y, None
            elif len(y) == 3:
                op, pat, args = y
            elif len(y) == 2:
                op = None
                pat, args = y

            if op == 'not':
                for j in range(i, len(self)):
                    if re.match(pat, self[j][0], flags=re.S):
                        pytest.fail(f"Should not have found {self[j][0]!r} matching {pat}")
                        return
                continue

            if op == 'eol':
                if i < len(self):
                    pytest.fail(f"Expected end of log; found {self[i]}")
                return

            while True:
                try:
                    x = self[i]
                    i += 1
                except IndexError:
                    pytest.fail(f"Not enough elements were logged looking for {pat}")
                if op == 'until' and not re.match(pat, x[0], flags=re.S):
                    continue
                if not pat:
                    assert not x[0]
                else:
                    assert re.match(pat, x[0], flags=re.S)
                if args is not None:
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
    def __init__(self, global_dir, installs=[]):
        self.global_dir = global_dir
        self.installs = list(installs)
        self.shebang_can_run_anything = True
        self.shebang_can_run_anything_silently = False

    def get_installs(self, *, include_unmanaged=True, set_default=True):
        return self.installs

    def get_install_to_run(self, tag):
        company, _, tag = tag.replace("/", "\\").rpartition("\\")
        return [i for i in self.installs
                if i["tag"] == tag and (not company or i["company"] == company)][0]


@pytest.fixture
def fake_config(tmp_path):
    return FakeConfig(tmp_path / "bin")


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



def make_install(tag, **kwargs):
    run_for = []
    for t in kwargs.get("run_for", [tag]):
        run_for.append({"tag": t, "target": kwargs.get("target", "python.exe")})
        run_for.append({"tag": t, "target": kwargs.get("targetw", "pythonw.exe"), "windowed": 1})

    i = {
        "company": kwargs.get("company", "PythonCore"),
        "id": "{}-{}".format(kwargs.get("company", "PythonCore"), tag),
        "sort-version": kwargs.get("sort_version", tag),
        "display-name": "{} {}".format(kwargs.get("company", "Python"), tag),
        "tag": tag,
        "install-for": [tag],
        "run-for": run_for,
        "prefix": PurePath(kwargs.get("prefix", rf"C:\{tag}")),
        "executable": kwargs.get("executable", "python.exe"),
    }
    try:
        i["alias"] = kwargs["alias"]
    except LookupError:
        pass
    return i


def fake_get_installs(install_dir):
    yield make_install("1.0")
    yield make_install("1.0-32", sort_version="1.0", alias=[dict(name="py1.0.exe"), dict(name="py1.0-32.exe")])
    yield make_install("1.0-64", sort_version="1.0", alias=[dict(name="py1.0.exe"), dict(name="py1.0-64.exe")])
    yield make_install("2.0-64", sort_version="2.0")
    yield make_install("2.0-arm64", sort_version="2.0")
    yield make_install("3.0a1-32", sort_version="3.0a1")
    yield make_install("3.0a1-64", sort_version="3.0a1")
    yield make_install("1.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("1.1-64", sort_version="1.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("1.1-arm64", sort_version="1.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("2.1", sort_version="2.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("2.1-64", sort_version="2.1", company="Company", target="company.exe", targetw="companyw.exe")


def fake_get_installs2(install_dir):
    yield make_install("1.0-32", sort_version="1.0")
    yield make_install("3.0a1-32", sort_version="3.0a1", run_for=["3.0.1a1-32", "3.0-32", "3-32"])
    yield make_install("3.0a1-64", sort_version="3.0a1", run_for=["3.0.1a1-64", "3.0-64", "3-64"])
    yield make_install("3.0a1-arm64", sort_version="3.0a1", run_for=["3.0.1a1-arm64", "3.0-arm64", "3-arm64"])


def fake_get_unmanaged_installs():
    return []


def fake_get_venv_install(virtualenv):
    raise LookupError


@pytest.fixture
def patched_installs(monkeypatch):
    monkeypatch.setattr(manage.installs, "_get_installs", fake_get_installs)
    monkeypatch.setattr(manage.installs, "_get_unmanaged_installs", fake_get_unmanaged_installs)
    monkeypatch.setattr(manage.installs, "_get_venv_install", fake_get_venv_install)


@pytest.fixture
def patched_installs2(monkeypatch):
    monkeypatch.setattr(manage.installs, "_get_installs", fake_get_installs2)
    monkeypatch.setattr(manage.installs, "_get_unmanaged_installs", fake_get_unmanaged_installs)
    monkeypatch.setattr(manage.installs, "_get_venv_install", fake_get_venv_install)
