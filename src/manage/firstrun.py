import os
import sys
import time


if __name__ == "__main__":
    __package__ = "manage"
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

    import _native
    if not hasattr(_native, "coinitialize"):
        import _native_test
        for k in dir(_native_test):
            if k[:1] not in ("", "_"):
                setattr(_native, k, getattr(_native_test, k))


from . import logging
from .pathutils import Path

LOGGER = logging.LOGGER


def _package_name():
    from _native import get_current_package
    return get_current_package()


def check_app_alias(cmd):
    LOGGER.debug("Checking app execution aliases")
    # Expected identities:
    # Side-loaded MSIX
    # * "PythonSoftwareFoundation.PythonManager_3847v3x7pw1km",
    # Store package
    # * "PythonSoftwareFoundation.PythonManager_qbz5n2kfra8p0",
    # Development build
    # * "PythonSoftwareFoundation.PythonManager_m8z88z54g2w36",
    # MSI/dev install
    # * None
    try:
        pkg = _package_name()
    except OSError:
        LOGGER.debug("Failed to get current package name.", exc_info=True)
        pkg = None
    if not pkg:
        LOGGER.debug("Check skipped: MSI install can't do this check")
        return "skip"

    from _native import read_alias_package
    LOGGER.debug("Checking for %s", pkg)
    root = Path(os.environ["LocalAppData"]) / "Microsoft/WindowsApps"
    for name in ["py.exe", "pyw.exe", "python.exe", "pythonw.exe", "python3.exe", "pymanager.exe"]:
        exe = root / name
        try:
            LOGGER.debug("Reading from %s", exe)
            package = read_alias_package(exe)
            LOGGER.debug("Package: %s", package)
            if package != pkg:
                LOGGER.debug("Check failed: package did not match identity")
                return False
        except FileNotFoundError:
            LOGGER.debug("Check failed: did not find %s", exe)
            return False
    LOGGER.debug("Check passed: aliases are correct")
    return True


def check_long_paths(cmd):
    LOGGER.debug("Checking long paths setting")
    import winreg
    try:
        with winreg.OpenKeyEx(winreg.HKEY_LOCAL_MACHINE,
                              r"System\CurrentControlSet\Control\FileSystem") as key:
            if winreg.QueryValueEx(key, "LongPathsEnabled") == (1, winreg.REG_DWORD):
                LOGGER.debug("Check passed: registry key is OK")
                return True
    except FileNotFoundError:
        pass
    LOGGER.debug("Check failed: registry key was missing or incorrect")
    return False


def check_py_on_path(cmd):
    LOGGER.debug("Checking for legacy py.exe on PATH")
    from _native import read_alias_package
    try:
        if not _package_name():
            LOGGER.debug("Check skipped: MSI install can't do this check")
            return "skip"
    except OSError:
        LOGGER.debug("Failed to get current package name.", exc_info=True)
        LOGGER.debug("Check skipped: can't do this check")
        return "skip"
    for p in os.environ["PATH"].split(";"):
        if not p:
            continue
        py = Path(p) / "py.exe"
        try:
            read_alias_package(py)
            LOGGER.debug("Check passed: found alias at %s", py)
            # We found the alias, so we're good
            return True
        except FileNotFoundError:
            pass
        except OSError:
            # Probably not an alias, so we're not good
            LOGGER.debug("Check failed: found %s on PATH", py)
            return False
    LOGGER.debug("Check passed: no py.exe on PATH at all")
    return True


def check_global_dir(cmd):
    LOGGER.debug("Checking for global dir on PATH")
    if not cmd.global_dir:
        LOGGER.debug("Check skipped: global dir is not configured")
        return "skip"
    for p in os.environ["PATH"].split(";"):
        if not p:
            continue
        if Path(p).absolute().match(cmd.global_dir):
            LOGGER.debug("Check passed: %s is on PATH", p)
            return True
    # In case user has updated their registry but not the terminal
    try:
        r = _check_global_dir_registry(cmd)
        if r:
            return r
    except Exception:
        LOGGER.debug("Failed to read PATH setting from registry", exc_info=True)
    LOGGER.debug("Check failed: %s not found in PATH", cmd.global_dir)
    return False


def _check_global_dir_registry(cmd):
    import winreg
    with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, "Environment") as key:
        path, kind = winreg.QueryValueEx(key, "Path")
    LOGGER.debug("Current registry path: %s", path)
    if kind == winreg.REG_EXPAND_SZ:
        path = os.path.expandvars(path)
    elif kind != winreg.REG_SZ:
        LOGGER.debug("Check skipped: PATH registry key is not a string.")
        return "skip"
    for p in path.split(";"):
        if not p:
            continue
        if Path(p).absolute().match(cmd.global_dir):
            LOGGER.debug("Check skipped: %s will be on PATH after restart", p)
            return True
    return False


def do_global_dir_on_path(cmd):
    import winreg
    added = notified = False
    try:
        LOGGER.debug("Adding %s to PATH", cmd.global_dir)
        with winreg.OpenKeyEx(winreg.HKEY_CURRENT_USER, "Environment") as key:
            initial, kind = winreg.QueryValueEx(key, "Path")
        LOGGER.debug("Initial path: %s", initial)
        if kind not in (winreg.REG_SZ, winreg.REG_EXPAND_SZ) or not isinstance(initial, str):
            LOGGER.debug("Value kind is %s and not REG_[EXPAND_]SZ. Aborting.")
            return
        for p in initial.split(";"):
            if not p:
                continue
            if p.casefold() == str(cmd.global_dir).casefold():
                LOGGER.debug("Path is already found.")
                return
        newpath = initial.rstrip(";")
        if newpath:
            newpath += ";"
        newpath += str(Path(cmd.global_dir).absolute())
        LOGGER.debug("New path: %s", newpath)
        # Expand the value and ensure we are found
        for p in os.path.expandvars(newpath).split(";"):
            if not p:
                continue
            if p.casefold() == str(cmd.global_dir).casefold():
                LOGGER.debug("Path is added successfully")
                break
        else:
            return

        with winreg.CreateKeyEx(winreg.HKEY_CURRENT_USER, "Environment",
                                access=winreg.KEY_READ|winreg.KEY_WRITE) as key:
            initial2, kind2 = winreg.QueryValueEx(key, "Path")
            if initial2 != initial or kind2 != kind:
                LOGGER.debug("PATH has changed while we were working. Aborting.")
                return
            winreg.SetValueEx(key, "Path", 0, kind, newpath)
            added = True

        from _native import broadcast_settings_change
        broadcast_settings_change()
        notified = True
    except Exception:
        LOGGER.debug("Failed to update PATH environment variable", exc_info=True)
    finally:
        if added and not notified:
            LOGGER.warn("Failed to notify of PATH environment variable change.")
            LOGGER.info("You may need to sign out or restart to see the changes.")
        elif not added:
            LOGGER.error("Failed to update PATH environment variable successfully.")
            LOGGER.info("You may add it yourself by opening 'Edit environment "
                        "variables' and adding this directory to 'PATH': !B!%s!W!",
                        cmd.global_dir)
        else:
            LOGGER.info("PATH has been updated, and will take effect after "
                        "opening a new terminal.")


def check_any_install(cmd):
    LOGGER.debug("Checking for any Python runtime install")
    if not cmd.get_installs(include_unmanaged=True, set_default=False):
        LOGGER.debug("Check failed: no installs found")
        return False
    LOGGER.debug("Check passed: installs found")
    return True


def do_install(cmd):
    from .commands import find_command
    try:
        inst_cmd = find_command(["install", "default", "--automatic"], cmd.root)
    except Exception:
        LOGGER.debug("Failed to find 'install' command.", exc_info=True)
        LOGGER.warn("We couldn't install right now.")
        LOGGER.info("Use !B!py install default!W! later to install.")
        sys.exit(1)
    else:
        try:
            inst_cmd.execute()
        except Exception:
            LOGGER.debug("Failed to run 'install' command.", exc_info=True)
            raise


class _Welcome:
    _shown = False
    def __call__(self):
        if not self._shown:
            self._shown = True
            LOGGER.print("!G!Welcome to the Python installation manager "
                         "configuration helper.!W!")


def line_break():
    LOGGER.print()
    LOGGER.print("!B!" + "*" * logging.CONSOLE_MAX_WIDTH + "!W!")
    LOGGER.print()


def first_run(cmd):
    if not cmd.enabled:
        return

    welcome = _Welcome()
    if cmd.explicit:
        welcome()

    shown_any = False

    if cmd.check_app_alias:
        r = check_app_alias(cmd)
        if not r:
            welcome()
            line_break()
            shown_any = True
            LOGGER.print("!Y!Your app execution alias settings are configured to launch "
                         "other commands besides 'py' and 'python'.!W!",
                         level=logging.WARN)
            LOGGER.print("\nThis can be fixed by opening the '!B!Manage app "
                         "execution aliases!W!' settings page and enabling each "
                         "item labelled '!B!Python (default)!W!' and '!B!Python "
                         "install manager!W!'.\n", wrap=True)
            if (
                cmd.confirm and
                not cmd.ask_ny("Open Settings now, so you can modify !B!App "
                               "execution aliases!W!?")
            ):
                os.startfile("ms-settings:advanced-apps")
                LOGGER.print("\nThe Settings app should be open. Navigate to the "
                            "!B!App execution aliases!W! page and scroll to the "
                            "'!B!Python!W!' entries to enable the new commands.",
                            wrap=True)
        elif cmd.explicit:
            if r == "skip":
                LOGGER.info("Skipped app execution aliases check")
            else:
                LOGGER.info("Checked app execution aliases")

    if cmd.check_long_paths:
        if not check_long_paths(cmd):
            welcome()
            line_break()
            shown_any = True
            LOGGER.print("!Y!Windows is not configured to allow paths longer than "
                         "260 characters.!W!", level=logging.WARN)
            LOGGER.print("\nPython and some other apps can exceed this limit, "
                         "but it requires changing a system-wide setting, which "
                         "may need an administrator to approve, and will require a "
                         "reboot. Some packages may fail to install without long "
                         "path support enabled.\n", wrap=True)
            if cmd.confirm and not cmd.ask_ny("Update setting now?"):
                os.startfile(sys.executable, "runas", "**configure-long-paths", show_cmd=0)
                for _ in range(5):
                    time.sleep(0.25)
                    if check_long_paths(cmd):
                        LOGGER.info("The setting has been successfully updated.")
                        break
                else:
                    LOGGER.warn("The setting may not have been updated. Please "
                                "visit the additional help link at the end for "
                                "more assistance.")
        elif cmd.explicit:
            LOGGER.info("Checked system long paths setting")

    if cmd.check_py_on_path:
        r = check_py_on_path(cmd)
        if not r:
            welcome()
            line_break()
            shown_any = True
            LOGGER.print("!Y!The legacy 'py' command is still installed.!W!", level=logging.WARN)
            LOGGER.print("\nThis may interfere with launching the new 'py' "
                         "command, and may be resolved by uninstalling "
                         "'!B!Python launcher!W!'.\n", wrap=True)
            if (
                cmd.confirm and
                not cmd.ask_ny("Open Installed apps now?")
            ):
                os.startfile("ms-settings:appsfeatures")
        elif cmd.explicit:
            if r == "skip":
                LOGGER.info("Skipped check for legacy 'py' command")
            else:
                LOGGER.info("Checked PATH for legacy 'py' command")

    if cmd.check_global_dir:
        r = check_global_dir(cmd)
        if not r:
            welcome()
            line_break()
            shown_any = True
            LOGGER.print("!Y!The directory for versioned Python commands is not "
                         "configured.!W!", level=logging.WARN)
            LOGGER.print("\nThis will prevent commands like !B!python3.14.exe!W! "
                         "working, but will not affect the !B!python!W! or "
                         "!B!py!W! commands (for example, !B!py -V:3.14!W!).",
                         wrap=True)
            LOGGER.print("\nWe can add the directory to PATH now, but you will "
                         "need to restart your terminal to see the change, and "
                         "must manually edit environment variables to later "
                         "remove the entry.\n", wrap=True)
            if (
                cmd.confirm and
                not cmd.ask_ny("Add commands directory to your PATH now?")
            ):
                do_global_dir_on_path(cmd)
        elif cmd.explicit:
            if r == "skip":
                LOGGER.info("Skipped check for commands directory on PATH")
            else:
                LOGGER.info("Checked PATH for versioned commands directory")

    # This check must be last, because 'do_install' will exit the program.
    if cmd.check_any_install:
        if not check_any_install(cmd):
            welcome()
            line_break()
            shown_any = True
            LOGGER.print("!Y!You do not have any Python runtimes installed.!W!",
                         level=logging.WARN)
            LOGGER.print("\nInstall the current latest version of CPython? If "
                         "not, you can use !B!py install default!W! later to "
                         "install, or one will be installed automatically when "
                         "needed.\n", wrap=True)
            LOGGER.info("")
            if cmd.ask_yn("Install CPython now?"):
                do_install(cmd)
        elif cmd.explicit:
            LOGGER.info("Checked for any Python installs")

    if shown_any or cmd.explicit:
        line_break()
        LOGGER.print("!G!Configuration checks completed.!W!", level=logging.WARN)
        LOGGER.print("\nTo run these checks again, launch !B!Python install "
                     "manager!W! from your Start menu, or !B!py install "
                     "--configure!W! from the terminal.", wrap=True)
        line_break()


if __name__ == "__main__":
    class TestCommand:
        enabled = True
        global_dir = Path(os.path.expandvars(r"%LocalAppData%\Python\bin"))
        explicit = False
        confirm = True
        check_app_alias = True
        check_long_paths = True
        check_py_on_path = True
        check_any_install = True
        check_global_dir = True
        check_default_tag = True

        def get_installs(self, *args, **kwargs):
            import json
            root = Path(os.path.expandvars(r"%LocalAppData%\Python"))
            result = []
            for d in root.iterdir():
                inst = d / "__install__.json"
                try:
                    result.append(json.loads(inst.read_text()))
                except FileNotFoundError:
                    pass
            return result

        def _ask(self, fmt, *args, yn_text="Y/n", expect_char="y"):
            if not self.confirm:
                return True
            LOGGER.print(f"{fmt} [{yn_text}] ", *args, end="")
            try:
                resp = input().casefold()
            except Exception:
                return False
            return not resp or resp.startswith(expect_char.casefold())

        def ask_yn(self, fmt, *args):
            "Returns True if the user selects 'yes' or confirmations are skipped."
            return self._ask(fmt, *args)

        def ask_ny(self, fmt, *args):
            "Returns True if the user selects 'no' or confirmations are skipped."
            return self._ask(fmt, *args, yn_text="y/N", expect_char="n")

    first_run(TestCommand())
