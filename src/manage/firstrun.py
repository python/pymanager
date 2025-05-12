import os
import sys

if __name__ == "__main__":
    __package__ = "manage"
    sys.path.append(os.path.dirname(os.path.dirname(__file__)))

    import _native
    if not hasattr(_native, "coinitialize"):
        import _native_test
        for k in dir(_native_test):
            if k[:1] not in ("", "_"):
                setattr(_native, k, getattr(_native_test, k))


from .logging import LOGGER
from .pathutils import Path


def check_app_alias(cmd):
    LOGGER.debug("Checking app execution aliases")
    from _native import read_alias_package
    root = Path(os.environ["LocalAppData"]) / "Microsoft/WindowsApps"
    for name in ["py.exe", "pyw.exe", "python.exe", "pythonw.exe", "python3.exe", "pymanager.exe"]:
        exe = root / name
        try:
            LOGGER.debug("Reading from %s", exe)
            package = (read_alias_package(exe) or "").split("\0")
            LOGGER.debug("Data: %r", package)
            if package[1] not in (
                # Side-loaded MSIX
                "PythonSoftwareFoundation.PythonManager_3847v3x7pw1km",
                # Store packaged
                "PythonSoftwareFoundation.PythonManager_qbz5n2kfra8p0",
                # Development build
                "PythonSoftwareFoundation.PythonManager_m8z88z54g2w36",
            ):
                LOGGER.debug("Check failed: package did not match identity")
        except FileNotFoundError:
            LOGGER.debug("Check failed: did not find %s", exe)
            return False
    LOGGER.debug("Check passed: aliases are correct")
    return True


def check_long_paths(cmd):
    LOGGER.debug("Checking long paths setting")
    import winreg
    try:
        with winreg.OpenKeyEx(winreg.HKEY_LOCAL_MACHINE, r"System\CurrentControlSet\Control\FileSystem") as key:
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


def check_global_dir(cmd):
    LOGGER.debug("Checking for global dir on PATH")
    if not cmd.global_dir:
        LOGGER.debug("Check passed: global dir is not configured")
        return True
    for p in os.environ["PATH"].split(";"):
        if not p:
            continue
        if Path(p).absolute().match(cmd.global_dir):
            LOGGER.debug("Check passed: %s is on PATH", p)
            return True
    LOGGER.debug("Check failed: %s not found in PATH", cmd.global_dir)
    return False


def do_global_dir_on_path(cmd):
    import winreg
    LOGGER.debug("Adding %s to PATH", cmd.global_dir)
    # TODO: Add to PATH (correctly!)
    # TODO: Send notification


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
    except Exception as ex:
        LOGGER.debug("Failed to find 'install' command.", exc_info=True)
        LOGGER.warn("We couldn't install right now.")
        LOGGER.info("Use !B!py install default!W! later to install.")
        sys.exit(1)
    else:
        try:
            inst_cmd.execute()
        except Exception as ex:
            LOGGER.debug("Failed to run 'install' command.", exc_info=True)
            raise


class _Welcome:
    _shown = False
    def __call__(self):
        if not self._shown:
            self._shown = True
            LOGGER.info("!G!Welcome to the Python installation manager "
                        "configuration helper.!W!")
            LOGGER.info("")


def first_run(cmd):
    if not cmd.enabled:
        return

    welcome = _Welcome()
    if cmd.explicit:
        welcome()

    if cmd.check_app_alias:
        if not check_app_alias(cmd):
            welcome()
            LOGGER.warn("Your app execution alias settings are configured to launch "
                        "other commands besides 'py' and 'python'.")
            LOGGER.info("This can be fixed by opening the '!B!Manage app execution "
                        "aliases!W!' settings page and enabling each item labelled "
                        "'!B!Python (default)!W!' and '!B!Python install manager!W!'.")
            if (
                cmd.confirm and
                not cmd.ask_ny("Open Settings now? (Select !B!App execution aliases!W! after opening)")
            ):
                os.startfile("ms-settings:advanced-apps")
        elif cmd.explicit:
            LOGGER.info("Checked app execution aliases")

    if cmd.check_long_paths:
        if not check_long_paths(cmd):
            welcome()
            LOGGER.warn("Windows is not configured to allow paths longer than "
                        "260 characters.")
            LOGGER.info("Python and some other apps can bypass this setting, but it "
                        "requires changing a system-wide setting and a reboot. "
                        "Some packages may fail to install without long path "
                        "support enabled.")
            if (
                cmd.confirm and
                not cmd.ask_ny("Update setting now? You may be prompted for "
                               "administrator credentials.")
            ):
                os.startfile(sys.executable, "runas", "**configure-long-paths", show_cmd=0)
        elif cmd.explicit:
            LOGGER.info("Checked system long paths setting")

    if cmd.check_py_on_path:
        if not check_py_on_path(cmd):
            welcome()
            LOGGER.warn("The legacy 'py' command is still installed.")
            LOGGER.info("This may interfere with launching the new 'py' command, "
                        "and may be resolved by uninstalling '!B!Python launcher!W!'.")
            if (
                cmd.confirm and
                not cmd.ask_ny("Open Installed apps now?")
            ):
                os.startfile("ms-settings:appsfeatures")
        elif cmd.explicit:
            LOGGER.info("Checked PATH for legacy 'py' command")

    if cmd.check_global_dir:
        if not check_global_dir(cmd):
            welcome()
            LOGGER.warn("The directory for versioned Python commands is not configured.")
            LOGGER.info("This will prevent commands like !B!python3.14.exe!W! "
                        "working, but will not affect the !B!python!W! or "
                        "!B!py!W! commands (for example, !B!py -V:3.14!W!).")
            LOGGER.info("We can add the directory to PATH now, but you will need "
                        "to restart your terminal to see the change, and may need "
                        "to manually edit your environment variables if you later "
                        "decide to remove the entry.")
            if (
                cmd.confirm and
                not cmd.ask_ny("Add commands directory to your PATH now?")
            ):
                do_global_dir_on_path(cmd)
        elif cmd.explicit:
            LOGGER.info("Checked PATH for versioned commands directory")

    # This check must be last, because 'do_install' will exit the program.
    if cmd.check_any_install:
        if not check_any_install(cmd):
            welcome()
            LOGGER.warn("You do not have any Python runtimes installed.")
            LOGGER.info("Install the current latest version of CPython? If not, "
                        "you can use !B!py install default!W! later to install, or "
                        "one will be installed automatically when needed.")
            if cmd.ask_yn("Install CPython now?"):
                do_install(cmd)
        elif cmd.explicit:
            LOGGER.info("Checked for any Python installs")

    if cmd.explicit:
        LOGGER.info("!G!All checks passed.!W!")


if __name__ == "__main__":
    class TestCommand:
        enabled = True
        global_dir = r".\test-bin"
        explicit = False
        confirm = True
        check_app_alias = True
        check_long_paths = True
        check_py_on_path = True
        check_any_install = True
        check_global_dir = True
        check_default_tag = True

        def get_installs(self, *args, **kwargs):
            return []

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
