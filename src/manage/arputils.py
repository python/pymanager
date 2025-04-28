import os
import time
import winreg

from .fsutils import rglob
from .logging import LOGGER
from .pathutils import Path

def _root():
    return winreg.CreateKey(
        winreg.HKEY_CURRENT_USER,
        r"Software\Microsoft\Windows\CurrentVersion\Uninstall"
    )

_self_cmd_cache = None


def _self_cmd():
    global _self_cmd_cache
    if _self_cmd_cache:
        return _self_cmd_cache
    appdata = os.getenv("LocalAppData")
    if not appdata:
        appdata = os.path.expanduser(r"~\AppData\Local")
    apps = Path(appdata) / r"Microsoft\WindowsApps"
    LOGGER.debug("Searching %s for pymanager.exe", apps)
    for d in apps.iterdir():
        if not d.match("PythonSoftwareFoundation.PythonManager_*"):
            continue
        cmd = d / "pymanager.exe"
        LOGGER.debug("Checking %s", cmd)
        if cmd.exists():
            _self_cmd_cache = cmd
            return cmd
    try:
        import _winapi
    except ImportError:
        pass
    else:
        return _winapi.GetModuleFileName(0)
    raise FileNotFoundError("Cannot determine uninstall command.")


def _size(root):
    total = 0
    for f in rglob(root, dirs=False, files=True):
        try:
            total += f.lstat().st_size
        except OSError:
            pass
    return total // 1024


# Mainly refactored out for patching during tests
def _set_value(key, name, value):
    if isinstance(value, int):
        winreg.SetValueEx(key, name, None, winreg.REG_DWORD, value)
    else:
        winreg.SetValueEx(key, name, None, winreg.REG_SZ, str(value))


def _make(key, item, shortcut):
    prefix = Path(item["prefix"])

    for value, from_dict, value_name, relative_to in [
        (1, None, "ManagedByPyManager", None),
        (1, None, "NoModify", None),
        (1, None, "NoRepair", None),
        ("prefix", item, "InstallLocation", None),
        ("executable", item, "DisplayIcon", prefix),
        ("display-name", item, "DisplayName", None),
        ("company", item, "Publisher", None),
        ("tag", item, "DisplayVersion", None),
        ("DisplayIcon", shortcut, "DisplayIcon", prefix),
        ("DisplayName", shortcut, "DisplayName", None),
        ("Publisher", shortcut, "Publisher", None),
        ("DisplayVersion", shortcut, "DisplayVersion", None),
        ("HelpLink", shortcut, "HelpLink", None),
    ]:
        if from_dict is not None:
            try:
                value = from_dict[value]
            except LookupError:
                continue
        if relative_to:
            value = relative_to / value
        _set_value(key, value_name, value)

    try:
        from _native import date_as_str
        _set_value(key, "InstallDate", date_as_str())
    except Exception:
        LOGGER.debug("Unexpected error writing InstallDate", exc_info=True)
    try:
        _set_value(key, "EstimatedSize", _size(prefix))
    except Exception:
        LOGGER.debug("Unexpected error writing EstimatedSize", exc_info=True)

    item_id = item["id"]
    _set_value(key, "UninstallString", f'"{_self_cmd()}" uninstall --yes --by-id "{item_id}"')


def _delete_key(key, name):
    for retries in range(5):
        try:
            winreg.DeleteKey(key, name)
            break
        except PermissionError:
            time.sleep(0.01)
        except FileNotFoundError:
            pass
        except OSError as ex:
            LOGGER.debug("Unexpected error deleting registry key %s: %s", name, ex)

def _iter_keys(key):
    if not key:
        return
    for i in range(0, 32768):
        try:
            yield winreg.EnumKey(key, i)
        except OSError:
            return


def create_one(install, shortcut):
    with _root() as root:
        install_id = f"pymanager-{install['id']}"
        LOGGER.debug("Creating ARP entry for %s", install_id)
        try:
            with winreg.CreateKey(root, install_id) as key:
                _make(key, install, shortcut)
        except OSError:
            LOGGER.debug("Failed to create entry for %s", install_id)
            LOGGER.debug("TRACEBACK:", exc_info=True)
            _delete_key(root, install_id)
            raise


def cleanup(preserve_installs):
    keep = {f"pymanager-{i['id']}".casefold() for i in preserve_installs}
    to_delete = []
    with _root() as root:
        for key in _iter_keys(root):
            if not key.startswith("pymanager-") or key.casefold() in keep:
                continue
            try:
                with winreg.OpenKey(root, key) as subkey:
                    if winreg.QueryValueEx(subkey, "ManagedByPyManager")[0]:
                        to_delete.append(key)
            except FileNotFoundError:
                pass
            except OSError:
                LOGGER.verbose("Failed to clean up entry for %s", key)
                LOGGER.debug("TRACEBACK:", exc_info=True)
        for key in to_delete:
            try:
                LOGGER.debug("Removing ARP registration for %s", key)
                _delete_key(root, key)
            except FileNotFoundError:
                pass
            except OSError:
                LOGGER.verbose("Failed to clean up entry for %s", key)
                LOGGER.debug("TRACEBACK:", exc_info=True)
