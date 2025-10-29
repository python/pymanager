import os
import pytest
import winreg

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


def test_check_latest_install(fake_config, monkeypatch):
    fake_config.default_tag = "1"
    fake_config.default_platform = "-64"
    assert firstrun.check_latest_install(fake_config) == False

    fake_config.installs.append({"tag": "1.0-64"})
    assert firstrun.check_latest_install(fake_config) == False

    def _fallbacks(cmd):
        return [{"install-for": ["1.0-64"]}]

    monkeypatch.setattr(firstrun, "_list_available_fallback_runtimes", _fallbacks)
    assert firstrun.check_latest_install(fake_config) == True

    def _fallbacks(cmd):
        return [{"install-for": ["1.0-32"]}]

    monkeypatch.setattr(firstrun, "_list_available_fallback_runtimes", _fallbacks)
    assert firstrun.check_latest_install(fake_config) == False


def test_welcome(assert_log):
    welcome = firstrun._Welcome()
    assert_log(assert_log.end_of_log())
    welcome()
    assert_log(".*Welcome.*", "", r"!B!\*+!W!", "", assert_log.end_of_log())
    welcome()
    assert_log(".*Welcome.*", "", r"!B!\*+!W!", "", assert_log.end_of_log())



def test_firstrun_command(monkeypatch):
    from manage import commands

    called_first_run = False
    called_show_usage = False

    def fake_first_run(*args):
        nonlocal called_first_run
        called_first_run = True

    def fake_show_usage(*args):
        nonlocal called_show_usage
        called_show_usage = True

    monkeypatch.setattr(firstrun, "first_run", fake_first_run)
    monkeypatch.setattr(commands.FirstRun, "confirm", False)
    monkeypatch.setattr(commands.FirstRun, "show_usage", fake_show_usage)
    cmd = commands.find_command(["**first_run"], None)
    cmd.execute()
    assert called_first_run
    assert called_show_usage


def test_install_configure_command(monkeypatch):
    from manage import commands

    called_first_run = False
    called_show_usage = False

    def fake_first_run(*args):
        nonlocal called_first_run
        called_first_run = True

    def fake_show_usage(*args):
        nonlocal called_show_usage
        called_show_usage = True

    monkeypatch.setattr(firstrun, "first_run", fake_first_run)
    monkeypatch.setattr(commands.FirstRun, "confirm", False)
    monkeypatch.setattr(commands.FirstRun, "show_usage", fake_show_usage)
    cmd = commands.find_command(["install", "--configure"], None)
    cmd.execute()
    assert called_first_run
    assert not called_show_usage


def _create_key_read_only(key, subkey, *args, **kwargs):
    return winreg.OpenKeyEx(key, subkey)


def _raise_oserror(*args, **kwargs):
    raise OSError("injected error")


@pytest.fixture
def protect_reg(monkeypatch):
    import _native
    monkeypatch.setattr(winreg, "CreateKeyEx", _create_key_read_only)
    monkeypatch.setattr(winreg, "SetValueEx", _raise_oserror)
    monkeypatch.setattr(_native, "broadcast_settings_change", lambda *a: None)


def test_do_global_dir_open_fail(protect_reg, fake_config, assert_log, monkeypatch):
    monkeypatch.setattr(winreg, "OpenKeyEx", _raise_oserror)
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(assert_log.skip_until("Failed to update PATH.+"))


def test_do_global_dir_read_fail(protect_reg, fake_config, assert_log, monkeypatch):
    monkeypatch.setattr(winreg, "QueryValueEx", _raise_oserror)
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(assert_log.skip_until("Failed to update PATH.+"))


def test_do_global_dir_read_kind_fail(protect_reg, fake_config, assert_log, monkeypatch):
    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: (100, winreg.REG_DWORD))
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(
        assert_log.skip_until("Initial path: %s", (100,)),
        ("Value kind is %s.+", (winreg.REG_DWORD,)),
    )


def test_do_global_dir_path_already_set(protect_reg, fake_config, assert_log, monkeypatch):
    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: (f"{fake_config.global_dir};b;c", winreg.REG_SZ))
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(assert_log.skip_until("Path is already found"))

    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: (f"a;{fake_config.global_dir};c", winreg.REG_SZ))
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(assert_log.skip_until("Path is already found"))

    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: (f"a;b;{fake_config.global_dir}", winreg.REG_SZ))
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(assert_log.skip_until("Path is already found"))


def test_do_global_dir_path_lost_race(protect_reg, fake_config, assert_log, monkeypatch):
    paths = ["a;b", "a;b;c"]
    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: (paths.pop(), winreg.REG_SZ))
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(
        assert_log.skip_until("New path: %s", None),
        "Path is added successfully",
        "PATH has changed.+",
    )


def test_do_global_dir_write_same_kind(protect_reg, fake_config, monkeypatch):
    saved = []
    monkeypatch.setattr(winreg, "SetValueEx", lambda *a: saved.append(a))

    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: ("a;", winreg.REG_SZ))
    firstrun.do_global_dir_on_path(fake_config)
    assert saved[-1][1:] == ("Path", 0, winreg.REG_SZ, f"a;{fake_config.global_dir}")

    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: ("a", winreg.REG_EXPAND_SZ))
    firstrun.do_global_dir_on_path(fake_config)
    assert saved[-1][1:] == ("Path", 0, winreg.REG_EXPAND_SZ, f"a;{fake_config.global_dir}")


def test_do_global_dir_path_fail_broadcast(protect_reg, fake_config, assert_log, monkeypatch):
    import _native
    monkeypatch.setattr(_native, "broadcast_settings_change", _raise_oserror)
    monkeypatch.setattr(winreg, "QueryValueEx", lambda *a: ("a;", winreg.REG_SZ))
    monkeypatch.setattr(winreg, "SetValueEx", lambda *a: None)
    firstrun.do_global_dir_on_path(fake_config)
    assert_log(assert_log.skip_until("Failed to notify of PATH environment.+"))


def test_check_long_paths(registry, fake_config):
    assert not firstrun.check_long_paths(fake_config, hive=registry.hive, keyname=registry.root)
    registry.setup(LongPathsEnabled=1)
    assert firstrun.check_long_paths(fake_config, hive=registry.hive, keyname=registry.root)


def test_do_configure_long_paths(registry, fake_config, monkeypatch):
    firstrun.do_configure_long_paths(fake_config, hive=registry.hive, keyname=registry.root, startfile=_raise_oserror)
    assert winreg.QueryValueEx(registry.key, "LongPathsEnabled") == (1, winreg.REG_DWORD)


def test_do_configure_long_paths_elevated(protect_reg, fake_config, monkeypatch):
    startfile_calls = []
    def startfile(*a, **kw):
        startfile_calls.append((a, kw))
    # Pretend we can interact, so that os.startfile gets called
    fake_config.confirm = True
    firstrun.do_configure_long_paths(fake_config, startfile=startfile)
    assert startfile_calls
    assert startfile_calls[0][0][1:] == ("runas", "**configure-long-paths")
