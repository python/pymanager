import json
import os

from .exceptions import (
    ArgumentError,
    AutomaticInstallDisabledError,
    HashMismatchError,
    FilesInUseError,
    NoInstallFoundError,
)
from .fsutils import ensure_tree, rmtree, unlink
from .indexutils import Index
from .logging import CONSOLE_MAX_WIDTH, LOGGER, ProgressPrinter, VERBOSE
from .pathutils import Path, PurePath
from .tagutils import install_matches_any, tag_or_range
from .urlutils import (
    sanitise_url,
    urlopen as _urlopen,
    urlretrieve as _urlretrieve,
    IndexDownloader,
)


# In-process cache to save repeat downloads
DOWNLOAD_CACHE = {}


DEFAULT_SITE_DIRS = ["Lib\\site-packages", "Scripts"]

def _multihash(file, hashes):
    import hashlib
    LOGGER.debug("Calculating hashes: %s", ", ".join(hashes))
    hashers = [(hashlib.new(k), k, v) for k, v in hashes.items()]

    for chunk in iter(lambda: file.read(1024 * 1024), b""):
        for h in hashers:
            h[0].update(chunk)

    for h, alg, expect in hashers:
        actual = h.hexdigest().casefold()
        expect = expect.casefold()
        if expect and actual != expect:
            raise HashMismatchError(f"Hash mismatch: {alg}:{actual} (expected {expect})")
        else:
            LOGGER.debug("%s digest: %s (matched)", alg, actual)


def _expand_versions_by_tag(versions):
    for v in versions:
        if isinstance(v["tag"], str):
            yield v
        else:
            for t in v["tag"]:
                yield {**v, "tag": t}


def select_package(index_downloader, tag, platform=None, *, urlopen=_urlopen, by_id=False):
    """Finds suitable package from index.json that looks like:
    {"versions": [
      {"id": ..., "company": ..., "tag": ..., "url": ..., "hash": {"sha256": hexdigest}},
      ...
    ]}
    tag may be a list of tags that are allowed to match exactly.
    """

    LOGGER.debug("Selecting package with tag=%s and platform=%s", tag, platform)
    first_exc = None
    for index in index_downloader:
        try:
            if by_id:
                for v in index.versions:
                    if v["id"].casefold() == tag.casefold():
                        return v
                raise LookupError("Could not find a runtime matching '{}' at '{}'".format(
                    tag, sanitise_url(index.source_url)
                ))
            if platform:
                try:
                    return index.find_to_install(tag + platform)
                except LookupError:
                    pass
            return index.find_to_install(tag)
        except LookupError as ex:
            first_exc = ex

    if first_exc:
        raise first_exc

    assert False, "unreachable code"
    raise RuntimeError("End of select_package reached")


def download_package(cmd, install, dest, cache, *, on_progress=None, urlopen=_urlopen, urlretrieve=_urlretrieve):
    LOGGER.debug("Starting download package %s to %s", sanitise_url(install["url"]), dest)

    if not cmd.force and dest.is_file():
        LOGGER.verbose("Download was found in the cache. (Pass --force to ignore cached downloads.)")
        try:
            validate_package(install, dest, delete=False)
        except HashMismatchError:
            LOGGER.info("Cached file could not be verified. Downloading it again.")
        else:
            LOGGER.debug("Download skipped because %s already exists", dest)
            return dest

    if cmd.bundled_dir:
        bundled = cmd.bundled_dir / dest.name
        if bundled.is_file():
            try:
                validate_package(install, bundled, delete=False)
            except HashMismatchError:
                LOGGER.debug("Bundled file at %s did not match expected hash.", bundled)
            else:
                LOGGER.verbose("Using bundled file at %s", bundled)
                return bundled

    unlink(dest, "Removing old download is taking some time. " + 
                 "Please continue to wait, or press Ctrl+C to abort.")

    def _find_creds(url):
        from .urlutils import extract_url_auth, unsanitise_url
        LOGGER.verbose("Finding credentials for %s.", url)
        auth = extract_url_auth(unsanitise_url(url, [cmd.source]))
        if auth:
            LOGGER.debug("Found credentials in URL or configured source.")
            return auth
        auth = os.getenv("PYMANAGER_USERNAME", ""), os.getenv("PYMANAGER_PASSWORD", "")
        if auth[0]:
            LOGGER.debug("Found credentials in environment.")
            return auth
        return None

    ensure_tree(dest)
    urlretrieve(install["url"], dest, on_progress=on_progress, on_auth_request=_find_creds)
    LOGGER.debug("Downloaded to %s", dest)
    return dest


def validate_package(install, dest, *, delete=True):
    if "hash" in install:
        LOGGER.debug("Starting hash validation of %s", dest)
        try:
            with open(dest, "rb") as f:
                _multihash(f, install["hash"])
        except HashMismatchError as ex:
            if not delete:
                raise
            unlink(dest, "Deleting downloaded files is taking some time. " +
                         "Please continue to wait, or press Ctrl+C to abort.")
            raise HashMismatchError() from ex
    else:
        LOGGER.debug("Skipping hash validation of %s because there is no hash "
                     "listed in the install data.", dest)


def extract_package(package, prefix, calculate_dest=Path, *, on_progress=None, repair=False):
    import zipfile

    LOGGER.debug("Starting extract of %s to %s", package, prefix)

    if not on_progress:
        def on_progress(*_): pass

    if package.match("*.nupkg"):
        def _calc(prefix, filename, calculate_dest=calculate_dest):
            if not filename.startswith("tools/"):
                return None
            return calculate_dest(prefix, *PurePath(filename).parts[1:])
        calculate_dest = _calc

    # TODO: Optimise/parallelise extract

    warn_out_of_prefix = []
    warn_overwrite = []
    with zipfile.ZipFile(package, "r") as zf:
        items = list(zf.infolist())
        total = len(items) if on_progress else 0
        for i, member in enumerate(items):
            on_progress((i * 100) // total)
            dest = calculate_dest(prefix, member.filename)
            if not dest:
                continue
            try:
                dest.relative_to(prefix)
            except ValueError:
                warn_out_of_prefix.append(dest)
                continue
            if repair:
                unlink(dest, "Deleting an existing file is taking some time. " +
                             "Please ensure Python is not running, and continue to wait " +
                             "or press Ctrl+C to abort (which will leave your install corrupted).")
            elif dest.exists():
                warn_overwrite.append(dest)
                continue
            ensure_tree(dest)
            with open(dest, "wb") as f:
                f.write(zf.read(member))
    on_progress(100)

    if warn_out_of_prefix:
        on_progress(None)
        LOGGER.warn("**********************************************************************")
        LOGGER.warn("Package attempted to extract outside of its prefix, but was prevented.")
        LOGGER.warn("THIS PACKAGE MAY BE MALICIOUS. Take care before using it, or uninstall")
        LOGGER.warn("it immediately.")
        LOGGER.warn("**********************************************************************")
        for dest in warn_out_of_prefix:
            LOGGER.debug("Attempted to create: %s", dest)
    if warn_overwrite:
        on_progress(None)
        LOGGER.warn("**********************************************************************")
        LOGGER.warn("Package attempted to overwrite existing item, but was prevented.")
        LOGGER.warn("THIS PACKAGE MAY BE MALICIOUS OR CORRUPT. Take care before using it,")
        LOGGER.warn("and report this issue to the provider.")
        LOGGER.warn("**********************************************************************")
        for dest in warn_overwrite:
            LOGGER.debug("Attempted to overwrite: %s", dest)


def _create_shortcut_pep514(cmd, install, shortcut):
    from .pep514utils import update_registry
    update_registry(cmd.pep514_root, install, shortcut, cmd.tags)


def _cleanup_shortcut_pep514(cmd, install_shortcut_pairs):
    from .pep514utils import cleanup_registry
    cleanup_registry(cmd.pep514_root, {s["Key"] for i, s in install_shortcut_pairs}, cmd.tags)


def _create_start_shortcut(cmd, install, shortcut):
    from .startutils import create_one
    create_one(cmd.start_folder, install, shortcut, cmd.tags)


def _cleanup_start_shortcut(cmd, install_shortcut_pairs):
    from .startutils import cleanup
    cleanup(cmd.start_folder, [s for i, s in install_shortcut_pairs], cmd.tags)


def _create_arp_entry(cmd, install, shortcut):
    # ARP = Add/Remove Programs
    from .arputils import create_one
    create_one(install, shortcut, cmd.tags)


def _cleanup_arp_entries(cmd, install_shortcut_pairs):
    from .arputils import cleanup
    cleanup([i for i, s in install_shortcut_pairs], cmd.tags)


def _create_entrypoints(cmd, install, shortcut):
    from .aliasutils import scan_and_create_entrypoints
    aliases_written = cmd.scratch.setdefault("aliasutils.create_alias.aliases_written", set())
    scan_and_create_entrypoints(cmd, install, shortcut, aliases_written)


def _cleanup_entrypoints(cmd, install_shortcut_pairs):
    # Entry point aliases are cleaned up with regular aliases
    pass


SHORTCUT_HANDLERS = {
    "pep514": (_create_shortcut_pep514, _cleanup_shortcut_pep514),
    "start": (_create_start_shortcut, _cleanup_start_shortcut),
    "uninstall": (_create_arp_entry, _cleanup_arp_entries),
    "site-dirs": (_create_entrypoints, _cleanup_entrypoints),
}


def update_all_shortcuts(cmd, *, _create_alias=None, _cleanup_alias=None):
    if not _create_alias:
        from .aliasutils import create_alias as _create_alias
    if not _cleanup_alias:
        from .aliasutils import cleanup_alias as _cleanup_alias

    LOGGER.debug("Updating global shortcuts")
    aliases_written = cmd.scratch["aliasutils.create_alias.aliases_written"] = set()
    shortcut_written = {}
    for i in cmd.get_installs():
        if cmd.global_dir:
            aliases = list(i.get("alias", ()))

            # Generate a python.exe for the default runtime in case the user
            # later disables/removes the global python.exe command.
            if i.get("default"):
                alias_1 = [a for a in aliases if not a.get("windowed")]
                alias_2 = [a for a in aliases if a.get("windowed")]
                if alias_1:
                    aliases.append({**alias_1[0], "name": "python.exe"})
                if alias_2:
                    aliases.append({**alias_2[0], "name": "pythonw.exe"})

            for a in aliases:
                target = i["prefix"] / a["target"]
                if not target.is_file():
                    LOGGER.warn("Skipping alias '%s' because target '%s' does not exist", a["name"], a["target"])
                    continue
                _create_alias(cmd, i, a, target, aliases_written)

        for s in i.get("shortcuts", ()):
            if cmd.enable_shortcut_kinds and s["kind"] not in cmd.enable_shortcut_kinds:
                continue
            if cmd.disable_shortcut_kinds and s["kind"] in cmd.disable_shortcut_kinds:
                continue
            try:
                create, cleanup = SHORTCUT_HANDLERS[s["kind"]]
            except LookupError:
                LOGGER.warn("Skipping invalid shortcut for '%s'", i["id"])
                LOGGER.debug("shortcut: %s", s)
            else:
                create(cmd, i, s)
                shortcut_written.setdefault(s["kind"], []).append((i, s))

        # Earlier releases may not have site_dirs. If not, assume defaults
        if ("site-dirs" in (cmd.enable_shortcut_kinds or ("site-dirs",)) and
            "site-dirs" not in (cmd.disable_shortcut_kinds or ()) and
            all(s["kind"] != "site-dirs" for s in i.get("shortcuts", ()))):

            create, cleanup = SHORTCUT_HANDLERS["site-dirs"]
            s = dict(kind="site-dirs", dirs=DEFAULT_SITE_DIRS)
            create(cmd, i, s)
            shortcut_written.setdefault("site-dirs", []).append((i, s))

    for k, (_, cleanup) in SHORTCUT_HANDLERS.items():
        cleanup(cmd, shortcut_written.get(k, []))

    _cleanup_alias(cmd, shortcut_written.get("site-dirs", []))


def print_cli_shortcuts(cmd):
    if cmd.global_dir and cmd.global_dir.is_dir() and any(cmd.global_dir.glob("*.exe")):
        try:
            if not any(cmd.global_dir.match(p) for p in os.getenv("PATH", "").split(os.pathsep) if p):
                LOGGER.info("")
                LOGGER.info("!B!Global shortcuts directory is not on PATH. " +
                            "Add it for easy access to global Python aliases.!W!")
                LOGGER.info("!B!Directory to add: !Y!%s!W!", cmd.global_dir)
                LOGGER.info("")
                return
        except Exception:
            LOGGER.debug("Failed to display PATH warning", exc_info=True)
            return

    from .installs import get_install_alias_names
    installs = cmd.get_installs()
    tags = getattr(cmd, "tags", None)
    seen = {"python.exe".casefold()}
    verbose = LOGGER.would_log_to_console(VERBOSE)
    for i in installs:
        # We need to pre-filter aliases before getting the nice names.
        aliases = [a for a in i.get("alias", ()) if a["name"].casefold() not in seen]
        seen.update(n["name"].casefold() for n in aliases)
        if not verbose:
            if i.get("default"):
                LOGGER.debug("%s will be launched by !G!python.exe!W!", i["display-name"])
            names = get_install_alias_names(aliases, windowed=True)
            LOGGER.debug("%s will be launched by %s", i["display-name"], ", ".join(names))

        if not install_matches_any(i, tags):
            continue

        names = get_install_alias_names(aliases, windowed=False)
        if i.get("default") and names:
            LOGGER.info("%s will be launched by !G!python.exe!W! and also %s",
                        i["display-name"], ", ".join(names))
        elif i.get("default"):
            LOGGER.info("%s will be launched by !G!python.exe!W!.", i["display-name"])
        elif names:
            LOGGER.info("%s will be launched by %s",
                        i["display-name"], ", ".join(names))
        else:
            LOGGER.info("Installed %s to %s", i["display-name"], i["prefix"])


def _same_install(i, j):
    return i["id"] == j["id"] and i["sort-version"] == j["sort-version"]


def _find_one(cmd, source, tag, *, installed=None, by_id=False):
    if by_id:
        LOGGER.debug("Searching for Python with ID %s", tag)
    elif tag:
        LOGGER.verbose("Searching for Python matching %s", tag)
    else:
        LOGGER.verbose("Searching for default Python version")

    downloader = IndexDownloader(source, Index, {}, DOWNLOAD_CACHE)
    install = select_package(downloader, tag, cmd.default_platform, by_id=by_id)

    if by_id:
        return install

    existing = [i for i in (installed or ()) if i["id"].casefold() == install["id"].casefold()]
    if not existing:
        return install

    if cmd.force:
        LOGGER.warn("Overwriting existing %s install because of --force.", existing[0]["display-name"])
        return install

    if cmd.repair:
        return existing[0]

    if cmd.update:
        if install["sort-version"] > existing[0]["sort-version"]:
            return install
        LOGGER.info("%s is already up to date.", existing[0]["display-name"])
        return None

    # Return the package if it was requested in a way that wouldn't have
    # selected the existing package (e.g. full version match)
    if (not _same_install(install, existing[0])
        and not install_matches_any(existing[0], [tag])):
        if cmd.ask_yn("!Y!Your existing %s install will be replaced by " +
                      "%s. Continue?!W!", existing[0]["display-name"],
                      install["display-name"]):
            return install
        LOGGER.debug("Not overwriting existing install.")
        return None

    LOGGER.info("%s is already installed.", existing[0]["display-name"])
    return None


def _download_one(cmd, source, install, download_dir, *, must_copy=False):
    package = download_dir / f"{install['id']}-{install['sort-version']}.zip"
    # Preserve nupkg extensions so we can directly reference Nuget packages
    if install["url"].casefold().endswith(".nupkg".casefold()):
        package = package.with_suffix(".nupkg")

    with ProgressPrinter("Downloading", maxwidth=CONSOLE_MAX_WIDTH) as on_progress:
        package = download_package(cmd, install, package, DOWNLOAD_CACHE, on_progress=on_progress)
    validate_package(install, package)
    if must_copy and package.parent != download_dir:
        import shutil
        dst = download_dir / package.name
        shutil.copyfile(package, dst)
        return dst
    return package


def _preserve_site(cmd, root, install):
    if not root.is_dir():
        return None
    if not cmd.preserve_site_on_upgrade:
        LOGGER.verbose("Not preserving site directory because of config")
        return None
    if cmd.force:
        LOGGER.verbose("Not preserving site directory because of --force")
        return None
    if cmd.repair:
        LOGGER.verbose("Not preserving site directory because of --repair")
        return None

    state = []
    i = 0

    site_dirs = DEFAULT_SITE_DIRS
    for s in install.get("shortcuts", ()):
        if s["kind"] == "site-dirs":
            site_dirs = s.get("dirs", ())
            break

    target_root = root.with_name(f"_{root.name}")
    target_root.mkdir(parents=True, exist_ok=True)

    for dirname in site_dirs:
        d = root / dirname
        if not d.is_dir():
            continue

        while True:
            target = target_root / str(i)
            i += 1
            try:
                unlink(target)
                break
            except FileNotFoundError:
                break
            except OSError:
                LOGGER.verbose("Failed to remove %s.", target)
        try:
            LOGGER.info("Preserving %s during update.", d.relative_to(root))
        except ValueError:
            # Just in case a directory goes weird, so we don't break
            LOGGER.verbose("Error information:", exc_info=True)
        LOGGER.verbose("Moving %s to %s", d, target)
        try:
            d.rename(target)
        except OSError:
            LOGGER.warn("Failed to preserve %s during update.", d)
            LOGGER.verbose("Error information:", exc_info=True)
        else:
            state.append((d, target))
    # Append None, target_root last to clean up after restore is done
    state.append((None, target_root))
    return state


def _restore_site(cmd, state):
    if not state:
        return
    for dest, src in state:
        if not dest:
            LOGGER.verbose("Removing preserved directory at %s", src)
            try:
                rmtree(
                    src,
                    "Removing temporary files is taking some time. " +
                    "You can continue to wait or press Ctrl+C to abort. " +
                    "Python has been installed, but some harmless temporary " +
                    "files may remain on disk."
                )
            except KeyboardInterrupt:
                break
            continue
        LOGGER.verbose("Restoring %s from %s after update.", dest, src)
        try:
            for i in src.iterdir():
                if not i.is_dir() and not i.is_file():
                    LOGGER.verbose("Not restoring %s because it is not a " +
                                   "normal file or directory.", i)
                    continue
                d = dest / i.name
                if d.exists():
                    LOGGER.verbose("Not restoring %s because %s exists", i, d)
                    continue
                LOGGER.verbose("Restoring %s to %s", i, d)
                d.parent.mkdir(parents=True, exist_ok=True)
                i.rename(d)
            LOGGER.info("Restored %s", dest.name)
        except OSError:
            LOGGER.warn("Failed to restore %s during update.", dest)
            LOGGER.verbose("TRACEBACK", exc_info=True)


def _install_one(cmd, source, install, *, target=None):
    if cmd.repair:
        LOGGER.info("Repairing %s.", install['display-name'])
    elif cmd.update:
        LOGGER.info("Updating to %s.", install['display-name'])
    else:
        LOGGER.info("Installing %s.", install['display-name'])
    LOGGER.verbose("Tag: %s\\%s", install['company'], install['tag'])

    if cmd.dry_run:
        LOGGER.info("Skipping rest of install due to --dry-run")
        return

    package = _download_one(cmd, source, install, cmd.download_dir)

    dest = target or (cmd.install_dir / install["id"])

    preserved_site = _preserve_site(cmd, dest, install)

    LOGGER.verbose("Extracting %s to %s", package, dest)
    if not cmd.repair:
        try:
            rmtree(
                dest,
                "Removing the previous install is taking some time. " +
                "Ensure Python is not running, and continue to wait " +
                "or press Ctrl+C to abort.",
                remove_ext_first=("exe", "dll", "json"),
            )
        except FileExistsError:
            LOGGER.error(
                "Unable to remove previous install. " +
                "Please check your packages directory at %s for issues.",
                dest.parent
            )
            raise
        except FilesInUseError:
            LOGGER.error(
                "Unable to remove previous install because files are still in use. " +
                "Please ensure Python is not currently running."
            )
            raise

    with ProgressPrinter("Extracting", maxwidth=CONSOLE_MAX_WIDTH) as on_progress:
        extract_package(package, dest, on_progress=on_progress, repair=cmd.repair)

    if target:
        unlink(
            dest / "__install__.json",
            "Removing metadata from the install is taking some time. Please " +
            "continue to wait, or press Ctrl+C to abort."
        )
    else:
        try:
            with open(dest / "__install__.json", "r", encoding="utf-8-sig") as f:
                LOGGER.debug("Updating from __install__.json in %s", dest)
                for k, v in json.load(f).items():
                    if not install.setdefault(k, v):
                        install[k] = v
        except FileNotFoundError:
            pass
        except (TypeError, ValueError):
            LOGGER.error(
                "Invalid data found in bundled install data. " +
                "Please report this to the provider of your package."
            )
            raise

        if "shortcuts" in install:
            # This saves our original set of shortcuts, so a later repair operation
            # can enable those that were originally disabled.
            shortcuts = install.setdefault("__original-shortcuts", install["shortcuts"])
            if cmd.enable_shortcut_kinds:
                shortcuts = [s for s in shortcuts
                             if s["kind"] in cmd.enable_shortcut_kinds]
            if cmd.disable_shortcut_kinds:
                shortcuts = [s for s in shortcuts
                             if s["kind"] not in cmd.disable_shortcut_kinds]
            install["shortcuts"] = shortcuts

        install["url"] = sanitise_url(install["url"])
        if source != cmd.fallback_source:
            install["source"] = sanitise_url(source)

        LOGGER.debug("Write __install__.json to %s", dest)
        with open(dest / "__install__.json", "w", encoding="utf-8") as f:
            json.dump(install, f, default=str)

    _restore_site(cmd, preserved_site)

    LOGGER.verbose("Install complete")


def _merge_existing_index(versions, index_json):
    try:
        with open(index_json, "r", encoding="utf-8") as f:
            existing_index = json.load(f)
        list(existing_index["versions"])
    except FileNotFoundError:
        pass
    except (json.JSONDecodeError, KeyError, ValueError):
        LOGGER.warn("Existing index file appeared invalid and was overwritten.")
        LOGGER.debug("TRACEBACK", exc_info=True)
    else:
        LOGGER.debug("Merging into existing %s", index_json)
        current = {i["url"].casefold() for i in versions}
        for install in existing_index["versions"]:
            if install.get("url", "").casefold() not in current:
                LOGGER.debug("Merging %s", install.get("url", "<unspecified>"))
                versions.append(install)


def _fatal_install_error(cmd, ex):
    logfile = cmd.get_log_file()
    if logfile:
        LOGGER.error("An error occurred. Please check any output above, "
                     "or the log file, and try again.")
        LOGGER.info("Log file for this session: !Y!%s!W!", logfile)
        LOGGER.info("If you cannot resolve it yourself, please report the error with "
                    "your log file at https://github.com/python/pymanager")
    else:
        LOGGER.error("An error occurred. Please check any output above, "
                     "and try again with -vv for more information.")
        LOGGER.info("If you cannot resolve it yourself, please report the error with "
                    "verbose output file at https://github.com/python/pymanager")
    LOGGER.debug("TRACEBACK:", exc_info=True)
    raise SystemExit(getattr(ex, "winerror", getattr(ex, "errno", 0)) or 1) from ex


def execute(cmd):
    LOGGER.debug("BEGIN install_command.execute: %r", cmd.args)

    cmd.tags = []

    if cmd.virtual_env:
        LOGGER.debug("Clearing virtual_env setting to avoid conflicts during install.")
        cmd.virtual_env = None

    if cmd.refresh:
        if cmd.args:
            LOGGER.warn("Ignoring arguments; --refresh always refreshes all installs.")
        if cmd.dry_run:
            LOGGER.info("Skipping shortcut refresh due to --dry-run")
        else:
            LOGGER.info("Refreshing install registrations.")
            update_all_shortcuts(cmd)
            print_cli_shortcuts(cmd)
            LOGGER.debug("END install_command.execute")
        return

    if cmd.force:
        # Ensure we always do clean installs when --force specified
        cmd.repair = False
        cmd.update = False

    if cmd.automatic:
        if not cmd.automatic_install:
            LOGGER.debug("automatic_install is not set - exiting")
            raise AutomaticInstallDisabledError()
        LOGGER.info("!B!" + "*" * CONSOLE_MAX_WIDTH + "!W!")

    download_index = {"versions": []}

    if not cmd.by_id:
        for arg in cmd.args:
            if arg.casefold() == "default".casefold():
                LOGGER.debug("Replacing 'default' with '%s'", cmd.default_install_tag)
                cmd.tags.append(tag_or_range(cmd.default_install_tag))
            else:
                try:
                    cmd.tags.append(tag_or_range(arg))
                except ValueError as ex:
                    LOGGER.warn("%s", ex)

        if not cmd.tags and cmd.automatic:
            cmd.tags = [tag_or_range(cmd.default_install_tag)]
    else:
        if cmd.from_script:
            raise ArgumentError("Cannot use --by-id and --from-script together")
        cmd.tags = [arg.casefold() for arg in cmd.args]
        if not cmd.tags:
            raise ArgumentError("One or more IDs are required with --by-id")


    try:
        if cmd.target:
            if len(cmd.tags) > 1:
                raise ArgumentError("Unable to install multiple versions with --target")
            try:
                tag = cmd.tags[0]
            except IndexError:
                if cmd.default_install_tag:
                    LOGGER.debug("No tags provided, installing default tag %s", cmd.default_install_tag)
                    tag = cmd.default_install_tag
                else:
                    LOGGER.debug("No tags provided, installing first runtime in feed")
                    tag = None

            try:
                first_exc = None
                for source in [cmd.source, cmd.fallback_source]:
                    if not source:
                        continue
                    try:
                        install = _find_one(cmd, source, tag, by_id=cmd.by_id)
                        break
                    except LookupError:
                        LOGGER.error("Failed to find a suitable install for '%s'.", tag)
                        raise NoInstallFoundError()
                    except Exception as ex:
                        LOGGER.debug("Capturing error in case fallbacks fail", exc_info=True)
                        first_exc = first_exc or ex
                else:
                    if first_exc:
                        raise first_exc
                    # Reachable if all sources are blank
                    raise RuntimeError("All install sources failed, nothing can be installed.")
                if install:
                    _install_one(cmd, source, install, target=Path(cmd.target))
                return
            except Exception as ex:
                return _fatal_install_error(cmd, ex)

        if cmd.from_script:
            # Have already checked that we are not using --by-id
            from .scriptutils import find_install_from_script
            try:
                spec = find_install_from_script(cmd, cmd.from_script)
            except LookupError:
                spec = None
            if spec:
                cmd.tags.append(tag_or_range(spec))
            else:
                cmd.tags.append(tag_or_range(cmd.default_install_tag))

        installed = list(cmd.get_installs())

        if cmd.download:
            if cmd.force:
                rmtree(cmd.download)
            cmd.download.mkdir(exist_ok=True, parents=True)
            # Do not check for existing installs
            installed = []

        try:
            if not cmd.tags:
                if cmd.repair:
                    LOGGER.verbose("No tags provided, repairing all installs:")
                    for install in installed:
                        # Only try to redownload from the same source
                        _install_one(cmd, install.get('source'), install)
                    # Fallthrough is safe - cmd.tags is empty
                elif cmd.update:
                    LOGGER.verbose("No tags provided, updating all installs:")
                    for install in installed:
                        first_exc = None
                        update = None
                        for source in [install.get('source'), cmd.source, cmd.fallback_source]:
                            if not source:
                                continue
                            try:
                                update = _find_one(cmd, source, install['id'], by_id=True)
                                if update:
                                    break
                            except LookupError:
                                LOGGER.error("Failed to find a suitable update for '%s'.", install['id'])
                                raise NoInstallFoundError()
                            except Exception as ex:
                                LOGGER.debug("Capturing error in case fallbacks fail", exc_info=True)
                                first_exc = first_exc or ex
                        else:
                            if first_exc:
                                raise first_exc
                            # Reachable if all sources are blank
                            raise RuntimeError("All install sources failed, nothing can be updated.")
                        if update and update["sort-version"] > install["sort-version"]:
                            _install_one(cmd, source, update)
                        else:
                            LOGGER.verbose(
                                "No new version available for %s\\%s '%s'.",
                                install["company"], install["tag"],
                                install["display-name"],
                            )
                    # Fallthrough is safe - cmd.tags is empty
                else:
                    raise ArgumentError("Specify at least one tag to install, or 'default' for "
                                        "the latest recommended release.")

            installs = []
            first_exc = None
            for source in [cmd.source, cmd.fallback_source]:
                if not source:
                    continue
                LOGGER.debug("Searching %s", source)
                try:
                    for tag in cmd.tags:
                        install = _find_one(cmd, source, tag, installed=installed, by_id=cmd.by_id)
                        if install:
                            installs.append(install)
                    break
                except LookupError:
                    LOGGER.error("Failed to find a suitable install for '%s'.", tag)
                    raise NoInstallFoundError()
                except (AssertionError, AttributeError, TypeError):
                    # These errors should never happen.
                    raise
                except Exception as ex:
                    LOGGER.debug("Capturing error in case fallbacks fail", exc_info=True)
                    first_exc = first_exc or ex
            else:
                if first_exc:
                    raise first_exc
                # Reachable if all sources are blank
                raise RuntimeError("All install sources failed, nothing can be installed.")
            for install in installs:
                if cmd.download:
                    LOGGER.info("Downloading %s", install["display-name"])
                    package = _download_one(cmd, source, install, cmd.download, must_copy=True)
                    download_index["versions"].append({
                        **install,
                        "url": package.name,
                    })
                else:
                    _install_one(cmd, source, install)
        except ArgumentError:
            raise
        except NoInstallFoundError as ex:
            raise SystemExit(1) from ex
        except Exception as ex:
            return _fatal_install_error(cmd, ex)

        if cmd.download:
            _merge_existing_index(download_index["versions"], cmd.download / "index.json")
            with open(cmd.download / "index.json", "w", encoding="utf-8") as f:
                json.dump(download_index, f, indent=2, default=str)
            LOGGER.info("Offline index has been generated at !Y!%s!W!.", cmd.download)
            LOGGER.info(
                "Use '!G!py install -s .\\%s [tags ...]!W!' to install from this index.",
                cmd.download.name
            )
        else:
            if cmd.dry_run:
                LOGGER.info("Skipping shortcut refresh due to --dry-run")
            else:
                update_all_shortcuts(cmd)
                if not cmd.automatic:
                    print_cli_shortcuts(cmd)

    finally:
        if cmd.automatic:
            LOGGER.info("To see all available commands, run '!G!py help!W!'")
            LOGGER.info("!B!" + "*" * CONSOLE_MAX_WIDTH + "!W!")

        LOGGER.debug("END install_command.execute")
