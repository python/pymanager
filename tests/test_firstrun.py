import os
import pytest

from pathlib import Path

from manage import firstrun
from _native import get_current_package, read_alias_package

def test_get_current_package():
    # The only circumstance where this may be different is if we're running
    # tests in a Store install of Python without a virtualenv. That should never
    # happen, because we run with 3.14 and there are no more Store installs.
    assert get_current_package() is None


def test_read_alias_package():
    # Hopefully there's at least one package add with an alias on this machine.
    root = Path(os.environ["LocalAppData"]) / "Microsoft/WindowsApps"
    if not root.is_dir() or not any(root.rglob("*.exe")):
        pytest.skip("Requires an installed app")
    for f in root.rglob("*.exe"):
        print("Reading package name from", f)
        p = read_alias_package(f)
        print("Read:", p)
        # One is sufficient
        return
    pytest.skip("Requires an installed app")


def fake_package_name():
    return "PythonSoftwareFoundation.PythonManager_m8z88z54g2w36"


def fake_package_name_error():
    raise OSError("injected failure")


def fake_package_name_none():
    return None


def test_check_app_alias(fake_config, monkeypatch):
    monkeypatch.setattr(firstrun, "_package_name", fake_package_name)
    assert firstrun.check_app_alias(fake_config) in (True, False)

    monkeypatch.setattr(firstrun, "_package_name", fake_package_name_error)
    assert firstrun.check_app_alias(fake_config) == "skip"

    monkeypatch.setattr(firstrun, "_package_name", fake_package_name_none)
    assert firstrun.check_app_alias(fake_config) == "skip"


def test_check_long_paths(fake_config):
    assert firstrun.check_long_paths(fake_config) in (True, False)


def test_check_py_on_path(fake_config, monkeypatch, tmp_path):
    monkeypatch.setattr(firstrun, "_package_name", fake_package_name)
    mp = monkeypatch.setitem(os.environ, "PATH", f";{tmp_path};")
    assert firstrun.check_py_on_path(fake_config) in (True, False)

    mp = monkeypatch.setitem(os.environ, "PATH", "")
    assert firstrun.check_py_on_path(fake_config) == True

    monkeypatch.setattr(firstrun, "_package_name", fake_package_name_error)
    assert firstrun.check_py_on_path(fake_config) == "skip"

    monkeypatch.setattr(firstrun, "_package_name", fake_package_name_none)
    assert firstrun.check_py_on_path(fake_config) == "skip"


def test_check_global_dir(fake_config, monkeypatch, tmp_path):
    fake_config.global_dir = None
    assert firstrun.check_global_dir(fake_config) == "skip"

    fake_config.global_dir = str(tmp_path)
    assert firstrun.check_global_dir(fake_config) == False

    monkeypatch.setattr(firstrun, "_check_global_dir_registry", lambda *a: "called")
    assert firstrun.check_global_dir(fake_config) == "called"

    # Some empty elements, as well as our "real" one
    monkeypatch.setitem(os.environ, "PATH", f";;{os.environ['PATH']};{tmp_path}")
    assert firstrun.check_global_dir(fake_config) == True


def test_check_global_dir_registry(fake_config, monkeypatch, tmp_path):
    fake_config.global_dir = str(tmp_path)
    assert firstrun._check_global_dir_registry(fake_config) == False
    # Deliberately not going to modify the registry for this test.
    # Integration testing will verify that it reads correctly.


def test_check_any_install(fake_config):
    assert firstrun.check_any_install(fake_config) == False

    fake_config.installs.append("an install")
    assert firstrun.check_any_install(fake_config) == True


def test_welcome(assert_log):
    welcome = firstrun._Welcome()
    assert_log(assert_log.end_of_log())
    welcome()
    assert_log(".*Welcome.*", "", assert_log.end_of_log())
    welcome()
    assert_log(".*Welcome.*", "", assert_log.end_of_log())
