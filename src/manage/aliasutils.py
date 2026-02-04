import os

from .exceptions import FilesInUseError, NoLauncherTemplateError
from .fsutils import atomic_unlink, ensure_tree, unlink
from .logging import LOGGER
from .pathutils import Path
from .tagutils import install_matches_any

_EXE = ".exe".casefold()

DEFAULT_SITE_DIRS = ["Lib\\site-packages", "Scripts"]

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


class AliasInfo:
    def __init__(self, **kwargs):
        self.install = kwargs.get("install")
        self.name = kwargs.get("name")
        self.windowed = kwargs.get("windowed", 0)
        self.target = kwargs.get("target")
        self.mod = kwargs.get("mod")
        self.func = kwargs.get("func")

    def replace(self, **kwargs):
        return AliasInfo(**{
            "install": self.install,
            "name": self.name,
            "windowed": self.windowed,
            "target": self.target,
            "mod": self.mod,
            "func": self.func,
            **kwargs,
        })

    @property
    def script_code(self):
        if self.mod and self.func:
            if not all(s.isidentifier() for s in self.mod.split(".")):
                LOGGER.warn("Alias %s has an entrypoint with invalid module "
                            "%r.", self.name, self.mod)
                return None
            if not all(s.isidentifier() for s in self.func.split(".")):
                LOGGER.warn("Alias %s has an entrypoint with invalid function "
                            "%r.", self.name, self.func)
                return None
            return SCRIPT_CODE.format(mod=self.mod, func=self.func)


def _if_exists(launcher, plat):
    suffix = "." + launcher.suffix.lstrip(".")
    plat_launcher = launcher.parent / f"{launcher.stem}{plat}{suffix}"
    if plat_launcher.is_file():
        return plat_launcher
    return launcher


def _create_alias(
    cmd,
    *,
    name,
    target,
    plat=None,
    windowed=0,
    script_code=None,
    allow_link=True,
    _link=os.link):
    p = cmd.global_dir / name
    if not p.match("*.exe"):
        p = p.with_name(p.name + ".exe")
    if not isinstance(target, Path):
        target = Path(target)
    ensure_tree(p)
    launcher = cmd.launcher_exe
    if windowed:
        launcher = cmd.launcherw_exe or launcher

    if plat:
        LOGGER.debug("Checking for launcher for platform -%s", plat)
        launcher = _if_exists(launcher, f"-{plat}")
    if not launcher.is_file():
        LOGGER.debug("Checking for launcher for default platform %s", cmd.default_platform)
        launcher = _if_exists(launcher, cmd.default_platform)
    if not launcher.is_file():
        LOGGER.debug("Checking for launcher for -64")
        launcher = _if_exists(launcher, "-64")
    LOGGER.debug("Create %s linking to %s using %s", name, target, launcher)
    if not launcher or not launcher.is_file():
        raise NoLauncherTemplateError()

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
    if not allow_link or not _link:
        # If links are disallowed, always replace the target with a copy.
        unlink(p)
        try:
            p.write_bytes(launcher_bytes)
            LOGGER.debug("Created %s as copy of %s", p.name, launcher.name)
            launcher_remap[launcher.name] = p
        except OSError:
            LOGGER.error("Failed to create global command %s.", name)
            LOGGER.debug("TRACEBACK", exc_info=True)
    elif existing_bytes == launcher_bytes:
        # Valid existing launcher, so save its path in case we need it later
        # for a hard link.
        launcher_remap.setdefault(launcher.name, p)
    else:
        # Links are allowed and we need to create one, so try to make a link,
        # falling back to a link to another existing alias (that we've checked
        # already during this run), and then falling back to a copy.
        # This handles the case where our links are on a different volume to the
        # install (so hard links don't work), but limits us to only a single
        # copy (each) of the redirector(s), thus saving space.
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
                    LOGGER.error("Failed to create global command %s.", name)
                    LOGGER.debug("TRACEBACK", exc_info=True)

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
            LOGGER.info("Failed to remove %s.", p_script)
            LOGGER.debug("TRACEBACK", exc_info=True)


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


def _scan_one(install, root):
    # Scan d for dist-info directories with entry_points.txt
    dist_info = [d for d in root.glob("*.dist-info") if d.is_dir()]
    entrypoints = [f for f in [d / "entry_points.txt" for d in dist_info] if f.is_file()]
    if len(entrypoints):
        LOGGER.debug("Found %i entry_points.txt files in %i dist-info in %s",
                     len(entrypoints), len(dist_info), root)

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
                    yield AliasInfo(install=install, name=name,
                                    mod=mod, func=func, **alias)


def _scan(install, prefix, dirs):
    for dirname in dirs or ():
        root = prefix / dirname
        yield from _scan_one(install, root)


def calculate_aliases(cmd, install, *, _scan=_scan):
    LOGGER.debug("Calculating aliases for %s", install["id"])

    prefix = install["prefix"]

    default_alias = None
    default_alias_w = None

    for a in install.get("alias", ()):
        target = prefix / a["target"]
        if not target.is_file():
            LOGGER.warn("Skipping alias '%s' because target '%s' does not exist",
                        a["name"], a["target"])
            continue
        ai = AliasInfo(install=install, **a)
        yield ai
        if a.get("windowed") and not default_alias_w:
            default_alias_w = ai
        if not default_alias:
            default_alias = ai

    if not default_alias_w:
        default_alias_w = default_alias

    if install.get("default"):
        if default_alias:
            yield default_alias.replace(name="python")
        if default_alias_w:
            yield default_alias_w.replace(name="pythonw", windowed=1)

    if not cmd.enable_entrypoints:
        return

    site_dirs = DEFAULT_SITE_DIRS
    for s in install.get("shortcuts", ()):
        if s.get("kind") == "site-dirs":
            site_dirs = s.get("dirs", ())
            break

    for ai in _scan(install, prefix, site_dirs):
        if ai.windowed and default_alias_w:
            yield ai.replace(target=default_alias_w.target)
        elif not ai.windowed and default_alias:
            yield ai.replace(target=default_alias.target)


def create_aliases(cmd, aliases, *, allow_link=True, _create_alias=_create_alias):
    if not cmd.global_dir:
        return

    written = set()

    LOGGER.debug("Creating aliases")

    for alias in aliases:
        if not alias.name:
            LOGGER.debug("Invalid alias info provided with no name.")
            continue

        n = alias.name.casefold().removesuffix(_EXE)
        if n in written:
            # We've already written this alias, so skip it.
            continue
        written.add(n)

        if not alias.target:
            LOGGER.debug("No suitable alias found for %s. Skipping", alias.name)
            continue

        target = alias.install["prefix"] / alias.target
        try:
            _create_alias(
                cmd,
                name=alias.name,
                plat=alias.install.get("tag", "").rpartition("-")[2],
                target=target,
                script_code=alias.script_code,
                windowed=alias.windowed,
                allow_link=allow_link,
            )
        except NoLauncherTemplateError:
            if install_matches_any(alias.install, getattr(cmd, "tags", None)):
                LOGGER.warn("Skipping %s alias because "
                            "the launcher template was not found.", alias.name)
            else:
                LOGGER.debug("Skipping %s alias because "
                             "the launcher template was not found.", alias.name)



def cleanup_aliases(cmd, *, preserve, _unlink_many=atomic_unlink):
    if not cmd.global_dir or not cmd.global_dir.is_dir():
        return

    LOGGER.debug("Cleaning up aliases")
    expected = set()
    for alias in preserve:
        if alias.name:
            n = alias.name.casefold().removesuffix(_EXE) + _EXE
            expected.add(n)

    LOGGER.debug("Retaining %d aliases", len(expected))
    for alias in cmd.global_dir.glob("*.exe"):
        if alias.name.casefold() in expected:
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
