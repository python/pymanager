import os

from .exceptions import FilesInUseError
from .fsutils import atomic_unlink, ensure_tree, unlink
from .logging import LOGGER
from .pathutils import Path
from .tagutils import install_matches_any

SCRIPT_CODE = """import sys

# Clear sys.path[0] if it contains this script.
# Be careful to use the most compatible Python code possible.
try:
    if sys.path[0]:
        if sys.argv[0].startswith(sys.path[0]):
            sys.path[0] = ""
        else:
            open(sys.path[0] + "/" + sys.argv[0], "rb").close()
            sys.path[0] = ""
except OSError:
    pass
except AttributeError:
    pass
except IndexError:
    pass

# Replace argv[0] with our executable instead of the script name.
try:
    if sys.argv[0][-14:].upper() == ".__SCRIPT__.PY":
        sys.argv[0] = sys.argv[0][:-14]
        sys.orig_argv[0] = sys.argv[0]
except AttributeError:
    pass
except IndexError:
    pass

from {mod} import {func}
sys.exit({func}())
"""

def _if_exists(launcher, plat):
    suffix = "." + launcher.suffix.lstrip(".")
    plat_launcher = launcher.parent / f"{launcher.stem}{plat}{suffix}"
    if plat_launcher.is_file():
        return plat_launcher
    return launcher


def create_alias(cmd, install, alias, target, *, script_code=None, _link=os.link):
    p = cmd.global_dir / alias["name"]
    if not p.match("*.exe"):
        p = p.with_name(p.name + ".exe")
    target = Path(target)
    ensure_tree(p)
    launcher = cmd.launcher_exe
    if alias.get("windowed"):
        launcher = cmd.launcherw_exe or launcher

    alias_written = cmd.scratch.setdefault("aliasutils.create_alias.alias_written", set())
    n = p.stem.casefold()
    if n in alias_written:
        # We've already written this alias in this session, so skip it.
        return
    alias_written.add(n)

    plat = install["tag"].rpartition("-")[-1]
    if plat:
        LOGGER.debug("Checking for launcher for platform -%s", plat)
        launcher = _if_exists(launcher, f"-{plat}")
    if not launcher.is_file():
        LOGGER.debug("Checking for launcher for default platform %s", cmd.default_platform)
        launcher = _if_exists(launcher, cmd.default_platform)
    if not launcher.is_file():
        LOGGER.debug("Checking for launcher for -64")
        launcher = _if_exists(launcher, "-64")
    LOGGER.debug("Create %s linking to %s using %s", alias["name"], target, launcher)
    if not launcher or not launcher.is_file():
        if install_matches_any(install, getattr(cmd, "tags", None)):
            LOGGER.warn("Skipping %s alias because the launcher template was not found.", alias["name"])
        else:
            LOGGER.debug("Skipping %s alias because the launcher template was not found.", alias["name"])
        return

    try:
        launcher_bytes = launcher.read_bytes()
    except OSError:
        warnings_shown = cmd.scratch.setdefault("aliasutils.create_alias.warnings_shown", set())
        if str(launcher) not in warnings_shown:
            LOGGER.warn("Failed to read launcher template at %s.", launcher)
            warnings_shown.add(str(launcher))
        LOGGER.debug("Failed to read %s", launcher, exc_info=True)
        return

    existing_bytes = b''
    try:
        with open(p, 'rb') as f:
            existing_bytes = f.read(len(launcher_bytes) + 1)
    except FileNotFoundError:
        pass
    except OSError:
        LOGGER.debug("Failed to read existing alias launcher.")

    launcher_remap = cmd.scratch.setdefault("aliasutils.create_alias.launcher_remap", {})
    if existing_bytes == launcher_bytes:
        # Valid existing launcher, so save its path in case we need it later
        # for a hard link.
        launcher_remap.setdefault(launcher.name, p)
    else:
        # First try and create a hard link
        unlink(p)
        try:
            _link(launcher, p)
            LOGGER.debug("Created %s as hard link to %s", p.name, launcher.name)
        except OSError as ex:
            if ex.winerror != 17:
                # Report errors other than cross-drive links
                LOGGER.debug("Failed to create hard link for command.", exc_info=True)
            launcher2 = launcher_remap.get(launcher.name)
            if launcher2:
                try:
                    _link(launcher2, p)
                    LOGGER.debug("Created %s as hard link to %s", p.name, launcher2.name)
                except FileNotFoundError:
                    raise
                except OSError:
                    LOGGER.debug("Failed to create hard link to fallback launcher")
                    launcher2 = None
            if not launcher2:
                try:
                    p.write_bytes(launcher_bytes)
                    LOGGER.debug("Created %s as copy of %s", p.name, launcher.name)
                    launcher_remap[launcher.name] = p
                except OSError:
                    LOGGER.error("Failed to create global command %s.", alias["name"])
                    LOGGER.debug(exc_info=True)

    p_target = p.with_name(p.name + ".__target__")
    do_update = True
    try:
        do_update = not target.match(p_target.read_text(encoding="utf-8"))
    except FileNotFoundError:
        pass
    except (OSError, UnicodeDecodeError):
        LOGGER.debug("Failed to read existing target path.", exc_info=True)

    if do_update:
        p_target.write_text(str(target), encoding="utf-8")

    p_script = p.with_name(p.name + ".__script__.py")
    if script_code:
        do_update = True
        try:
            do_update = p_script.read_text(encoding="utf-8") != script_code
        except FileNotFoundError:
            pass
        except (OSError, UnicodeDecodeError):
            LOGGER.debug("Failed to read existing script file.", exc_info=True)
        if do_update:
            p_script.write_text(script_code, encoding="utf-8")
    else:
        try:
            unlink(p_script)
        except OSError:
            LOGGER.error("Failed to clean up existing alias. Re-run with -v "
                         "or check the install log for details.")
            LOGGER.info("Failed to remove %s.", p_script, exc_info=True)


def _parse_entrypoint_line(line):
    line = line.partition("#")[0]
    name, sep, rest = line.partition("=")
    name = name.strip()
    if name and name[0].isalnum() and sep and rest:
        mod, sep, rest = rest.partition(":")
        mod = mod.strip()
        if mod and sep and rest:
            func, sep, extra = rest.partition("[")
            func = func.strip()
            if func:
                return name, mod, func
    return None, None, None


def _readlines(path):
    try:
        f = open(path, "r", encoding="utf-8", errors="strict")
    except OSError:
        LOGGER.debug("Failed to read %s", path, exc_info=True)
        return

    with f:
        try:
            while True:
                yield next(f)
        except StopIteration:
            return
        except UnicodeDecodeError:
            LOGGER.debug("Failed to decode contents of %s", path, exc_info=True)
            return


def _scan_one(root):
    # Scan d for dist-info directories with entry_points.txt
    dist_info = [d for d in root.glob("*.dist-info") if d.is_dir()]
    LOGGER.debug("Found %i dist-info directories in %s", len(dist_info), root)
    entrypoints = [f for f in [d / "entry_points.txt" for d in dist_info] if f.is_file()]
    LOGGER.debug("Found %i entry_points.txt files in %s", len(entrypoints), root)

    # Filter down to [console_scripts] and [gui_scripts]
    for ep in entrypoints:
        alias = None
        for line in _readlines(ep):
            if line.strip() == "[console_scripts]":
                alias = dict(windowed=0)
            elif line.strip() == "[gui_scripts]":
                alias = dict(windowed=1)
            elif line.lstrip().startswith("["):
                alias = None
            elif alias is not None:
                name, mod, func = _parse_entrypoint_line(line)
                if name and mod and func:
                    yield (
                        {**alias, "name": name},
                        SCRIPT_CODE.format(mod=mod, func=func),
                    )


def _scan(prefix, dirs):
    for dirname in dirs or ():
        root = prefix / dirname
        yield from _scan_one(root)


def scan_and_create_entrypoints(cmd, install, shortcut, *, _create_alias=create_alias, _scan=_scan):
    prefix = install["prefix"]

    # We will be called multiple times, so need to keep the list of names we've
    # already used in this session.
    known = cmd.scratch.setdefault("aliasutils.scan_and_create_entrypoints.known", set())

    aliases = list(install.get("alias", ()))
    alias_1 = [a for a in aliases if not a.get("windowed")]
    # If no windowed targets, we'll use the non-windowed one
    alias_2 = [a for a in aliases if a.get("windowed")] or alias_1

    targets = [
        (prefix / alias_1[0]["target"]) if alias_1 else None,
        (prefix / alias_2[0]["target"]) if alias_2 else None,
    ]

    if not any(targets):
        LOGGER.debug("No suitable alias found for %s. Skipping entrypoints",
                     install["id"])
        return

    for alias, code in _scan(prefix, shortcut.get("dirs")):
        # Only create names once per install command
        n = alias["name"].casefold()
        if n in known:
            continue
        known.add(n)

        # Copy the launcher template and create a standard __target__ file
        target = targets[1 if alias.get("windowed", 0) else 0]
        if not target:
            LOGGER.debug("No suitable alias found for %s. Skipping this " +
                         "entrypoint", alias["name"])
            continue
        _create_alias(cmd, install, alias, target, script_code=code)


def cleanup_alias(cmd, site_dirs_written, *, _unlink_many=atomic_unlink, _scan=_scan):
    if not cmd.global_dir or not cmd.global_dir.is_dir():
        return

    expected = set()
    for i in cmd.get_installs():
        expected.update(a.get("name", "").casefold() for a in i.get("alias", ()))

    for i, s in site_dirs_written or ():
        for alias, code in _scan(i["prefix"], s.get("dirs")):
            expected.add(alias.get("name", "").casefold())

    for alias in cmd.global_dir.glob("*.exe"):
        if alias.stem.casefold() in expected or alias.name.casefold() in expected:
            continue
        target = alias.with_name(alias.name + ".__target__")
        script = alias.with_name(alias.name + ".__script__.py")
        LOGGER.debug("Unlink %s", alias)
        try:
            _unlink_many([alias, target, script])
        except (OSError, FilesInUseError):
            LOGGER.warn("Failed to remove %s. Ensure it is not in use and run "
                        "py install --refresh to try again.", alias.name)
            LOGGER.debug("TRACEBACK", exc_info=True)
