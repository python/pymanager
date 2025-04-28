from .exceptions import (
    ArgumentError,
    AutomaticInstallDisabledError,
    NoInstallFoundError,
    NoInstallsError,
)
from .logging import LOGGER

try:
    from ._version import __version__
except ImportError:
    __version__ = "0.0"


# Will be overwritten by main.cpp on import
EXE_NAME = "py"

def _set_exe_name(name):
    global EXE_NAME
    EXE_NAME = name


__all__ = ["main", "NoInstallFoundError", "NoInstallsError", "find_one"]


def main(args, root=None):
    cmd = None
    delete_log = None
    try:
        from .commands import find_command, show_help
        args = list(args)
        if not root:
            from .pathutils import Path
            root = Path(args[0]).parent

        try:
            cmd = find_command(args[1:], root)
        except LookupError as ex:
            raise ArgumentError("Unrecognized command") from ex

        if cmd.show_help:
            cmd.help()
            return 0

        log_file = cmd.get_log_file()
        if log_file:
            LOGGER.file = open(log_file, "w", encoding="utf-8", errors="replace")
            LOGGER.verbose("Writing logs to %s", log_file)

        cmd.execute()
        if not cmd.keep_log:
            delete_log = log_file
    except AutomaticInstallDisabledError as ex:
        LOGGER.error("%s", ex)
        return ex.exitcode
    except ArgumentError as ex:
        if cmd:
            cmd.help()
        else:
            show_help(args[1:2])
        LOGGER.error("%s", ex)
        return 1
    except Exception as ex:
        LOGGER.error("INTERNAL ERROR: %s: %s", type(ex).__name__, ex)
        LOGGER.debug("TRACEBACK:", exc_info=True)
        return getattr(ex, "winerror", 0) or getattr(ex, "errno", 1)
    except SystemExit as ex:
        LOGGER.debug("SILENCED ERROR", exc_info=True)
        return ex.code
    finally:
        f, LOGGER.file = LOGGER.file, None
        if f:
            f.flush()
            f.close()
        if delete_log:
            try:
                delete_log.unlink()
            except OSError:
                pass
    return 0


def find_one(root, tag, script, windowed, allow_autoinstall, show_not_found_error):
    autoinstall_permitted = False
    try:
        from .commands import load_default_config
        from .scriptutils import quote_args
        i = None
        cmd = load_default_config(root)
        autoinstall_permitted = cmd.automatic_install
        LOGGER.debug("Finding runtime for '%s' or '%s'%s", tag, script, " (windowed)" if windowed else "")
        try:
            i = cmd.get_install_to_run(tag, script, windowed=windowed)
        except NoInstallsError:
            # We always allow autoinstall when there are no runtimes at all
            # (Noting that user preference may still prevent it)
            allow_autoinstall = True
            raise
        exe = str(i["executable"])
        args = quote_args(i.get("executable_args", ()))
        LOGGER.debug("Selected %s %s", exe, args)
        return exe, args
    except (NoInstallFoundError, NoInstallsError) as ex:
        if not autoinstall_permitted or not allow_autoinstall:
            LOGGER.error("%s", ex)
            raise AutomaticInstallDisabledError() from ex
        if show_not_found_error:
            LOGGER.error("%s", ex)
            LOGGER.debug("TRACEBACK:", exc_info=True)
        raise
    except Exception as ex:
        LOGGER.error("INTERNAL ERROR: %s: %s", type(ex).__name__, ex)
        LOGGER.debug("TRACEBACK:", exc_info=True)
        raise
    except SystemExit:
        LOGGER.debug("SILENCED ERROR", exc_info=True)
        raise
