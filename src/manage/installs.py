import json

from .exceptions import NoInstallFoundError, NoInstallsError
from .logging import DEBUG, LOGGER
from .pathutils import Path
from .tagutils import CompanyTag, tag_or_range, companies_match, split_platform
from .verutils import Version


def _make_sort_key(install):
    # Our sort key orders from most-preferred to least
    return (
        # Non-prereleases always sort last
        0 if not Version(install["sort-version"]).is_prerelease else 1,
        # Order by descending tags
        CompanyTag(install.get("company"), install.get("tag")),
    )


def _get_installs(install_dir):
    for d in Path(install_dir).iterdir():
        p = d / "__install__.json"
        try:
            with p.open() as f:
                j = json.load(f)
        except FileNotFoundError:
            continue

        if j.get("schema", 0) == 1:
            # HACK: to help transition alpha users from their existing installs
            try:
                j["display-name"] = j["displayName"]
            except LookupError:
                pass
            yield {
                **j,
                "prefix": p.parent,
                "executable": p.parent / j["executable"],
            }
        else:
            LOGGER.warn(
                "Unrecognized schema %s in %s. You may need to update.",
                j.get("schema", "None"),
                p,
            )
            continue


def _get_unmanaged_installs():
    from .pep514utils import get_unmanaged_installs
    return get_unmanaged_installs()


def _get_venv_install(virtual_env):
    if not virtual_env:
        raise LookupError
    venv = Path(virtual_env)
    try:
        pyvenv_cfg = (venv / "pyvenv.cfg").read_text("utf-8-sig", "ignore")
    except OSError as ex:
        raise LookupError from ex
    ver = [v.strip() for k, _, v in (s.partition("=") for s in pyvenv_cfg.splitlines())
           if k.strip().casefold() == "version".casefold()]
    return {
        "id": "__active-virtual-env",
        "display-name": "Active virtual environment",
        "sort-version": ver[0] if ver else "0.0",
        "company": "---",
        "tag": "(venv)",
        "default": True,
        "unmanaged": 1,
        "__any-platform": True,
        "alias": [
            {"name": "python.exe", "target": r"Scripts\python.exe"},
            {"name": "pythonw.exe", "target": r"Scripts\pythonw.exe", "windowed": 1},
        ],
        # Invalid tags, but the target will be used to determine whether to use
        # python.exe or pythonw.exe
        "run-for": [
            {"tag": "---", "target": r"Scripts\python.exe"},
            {"tag": "---", "target": r"Scripts\pythonw.exe", "windowed": 1},
        ],
        "prefix": Path(virtual_env),
        "executable": Path(virtual_env) / r"Scripts\python.exe",
    }


def get_installs(
    install_dir,
    include_unmanaged=True,
    virtual_env=None,
):
    LOGGER.debug("Reading installs from %s", install_dir)
    installs = list(_get_installs(install_dir))
    LOGGER.debug("Found %s %s", len(installs),
                 "install" if len(installs) == 1 else "installs")

    if include_unmanaged:
        LOGGER.debug("Reading unmanaged installs")
        try:
            um_installs = _get_unmanaged_installs()
        except Exception as ex:
            LOGGER.warn("Failed to read unmanaged installs: %s", ex)
            LOGGER.debug("TRACEBACK:", exc_info=True)
        else:
            LOGGER.debug("Found %s %s", len(um_installs),
                         "install" if len(um_installs) == 1 else "installs")
            installs.extend(um_installs)

    installs.sort(key=_make_sort_key)

    if virtual_env:
        LOGGER.debug("Checking for virtual environment at %s", virtual_env)
        try:
            installs.insert(0, _get_venv_install(virtual_env))
            LOGGER.debug("Found 1 install")
        except LookupError:
            LOGGER.debug("No virtual environment found")

    return installs


def _make_alias_key(alias):
    n1, sep, n3 = alias.rpartition(".")
    n2 = ""
    n3 = sep + n3

    n1, plat = split_platform(n1)

    while n1 and n1[-1] in "0123456789.-":
        n2 = n1[-1] + n2
        n1 = n1[:-1]

    if n1 and n1[-1].casefold() == "w".casefold():
        w = "w"
        n1 = n1[:-1]
    else:
        w = ""

    return n1, w, n2, plat, n3


def _make_opt_part(parts):
    if not parts:
        return ""
    if len(parts) == 1:
        return list(parts)[0]
    return "[{}]".format("|".join(sorted(p for p in parts if p)))


def _sk_sub(m):
    n = m.group(1)
    if not n:
        return ""
    if n in "[]":
        return ""
    try:
        return f"{int(n):020}"
    except ValueError:
        pass
    return n


def _make_alias_name_sortkey(n):
    import re
    return re.sub(r"(\d+|\[|\])", _sk_sub, n)


def get_install_alias_names(aliases, friendly=True, windowed=True):
    if not windowed:
        aliases = [a for a in aliases if not a.get("windowed")]
    if not friendly:
        return sorted(a["name"] for a in aliases)

    seen = {}
    has_w = {}
    plats = {}
    for n1, w, n2, plat, n3 in (_make_alias_key(a["name"]) for a in aliases):
        k = n1.casefold(), n2.casefold(), n3.casefold()
        seen.setdefault(k, (n1, n2, n3))
        has_w.setdefault(k, set()).add(w)
        plats.setdefault(k, set()).add(plat)

    result = []
    for k, (n1, n2, n3) in seen.items():
        result.append("".join([
            n1,
            _make_opt_part(has_w.get(k)),
            n2,
            _make_opt_part(plats.get(k)),
            n3,
        ]))
    return sorted(result, key=_make_alias_name_sortkey)


def _patch_install_to_run(i, run_for):
    return {
        **i,
        "executable": i["prefix"] / run_for["target"],
        "executable_args": run_for.get("args", ()),
    }


def get_matching_install_tags(
    installs,
    tag,
    windowed=None,
    default_platform=None,
    single_tag=False,
):
    exact_matches = []
    core_matches = []
    matches = []
    unmanaged_matches = []
    fallback_matches = []

    # Installs are in the correct order, so we'll first collect all the matches.
    # If no tag is provided, we still expand out the list by all of 'run-for'
    if tag:
        if isinstance(tag, str):
            tag = tag_or_range(tag)
        LOGGER.debug("Filtering installs by tag = %s", tag)
    for i in installs:
        matched_any = False
        for t in i.get("run-for", ()):
            ct = CompanyTag(i["company"], t["tag"])
            if tag and ct == tag:
                exact_matches.append((i, t))
                matched_any = True
            elif not tag or tag.satisfied_by(ct):
                if (
                    isinstance(tag, CompanyTag)
                    and not companies_match(tag.company, i["company"])
                ):
                    fallback_matches.append((i, t))
                    matched_any = True
                elif i.get("unmanaged"):
                    unmanaged_matches.append((i, t))
                    matched_any = True
                elif ct.is_core:
                    core_matches.append((i, t))
                    matched_any = True
                else:
                    matches.append((i, t))
                    matched_any = True
            if single_tag and matched_any:
                break
        if LOGGER.would_log_to_console(DEBUG):
            # Don't bother listing all installs unless the user has asked
            # for console output.
            if matched_any:
                LOGGER.debug("Filter included %s", i["id"])
            else:
                LOGGER.debug("Filter did not include %s", i["id"])

    best = [*exact_matches, *core_matches, *matches, *unmanaged_matches]

    if tag:
        LOGGER.debug("tag '%s' matched %s %s", tag, len(best),
                     "install" if len(best) == 1 else "installs")
        if exact_matches:
            LOGGER.debug("- %s exact match(es)", len(exact_matches))
        if core_matches:
            LOGGER.debug("- %s core install(s) by prefix", len(core_matches))
        if matches:
            LOGGER.debug("- %s non-core install(s) by prefix", len(matches))
        if unmanaged_matches:
            LOGGER.debug("- %s unmanaged install(s) by prefix", len(unmanaged_matches))
        if fallback_matches:
            LOGGER.debug("- %s additional installs by tag alone", len(fallback_matches))

    if not best and fallback_matches:
        best = fallback_matches

    # Filter for 'windowed' matches. If none, keep them all
    if windowed is not None:
        windowed = bool(windowed)
        best = [(i, t) for i, t in best if windowed == bool(t.get("windowed"))] or best
        LOGGER.debug("windowed = %s matched %s %s", windowed,
                     len(best), "install" if len(best) == 1 else "installs")

    # Filter for default_platform matches (by tag suffix).
    # If none or only prereleases, keep them all
    if default_platform:
        default_platform = default_platform.casefold()
        all_pre = all(Version(i["sort-version"]).is_prerelease for i, t in best)
        best2 = best
        best = [(i, t) for i, t in best
                if i.get("__any-platform")
                or t["tag"].casefold().endswith(default_platform)]
        LOGGER.debug("default_platform '%s' matched %s %s", default_platform,
                     len(best), "install" if len(best) == 1 else "installs")
        if (
            not best or
            (not all_pre and all(Version(i["sort-version"]).is_prerelease for i, t in best))
        ):
            LOGGER.debug("Reusing unfiltered list")
            best = best2

    return best


def get_install_to_run(
    install_dir,
    default_tag,
    tag,
    include_unmanaged=True,
    windowed=False,
    virtual_env=None,
    default_platform=None,
):
    """Returns the first install matching 'tag'.
    """
    installs = get_installs(
        install_dir,
        include_unmanaged=include_unmanaged,
        virtual_env=virtual_env,
    )

    if not installs:
        raise NoInstallsError

    if not tag or tag.casefold() == "default".casefold():
        # We know we want default, so try filtering first. If any are explicitly
        # tagged (e.g. active venv), they will be the only candidates.
        # Otherwise, we'll do a regular search as if 'default_tag' was provided.
        default_installs = [i for i in installs if i.get("default")]
        if default_installs:
            installs = default_installs
            tag = None
        else:
            tag = tag_or_range(default_tag)
        used_default = True
    else:
        tag = tag_or_range(tag)
        used_default = False

    best = get_matching_install_tags(
        installs,
        tag,
        windowed=windowed,
        default_platform=default_platform,
    )

    if best:
        return _patch_install_to_run(*best[0])

    if used_default:
        # It's legitimate to have no default runtime, but we're going to treat
        # it as if you have none at all. That way we get useful auto-install
        # behaviour.
        raise NoInstallsError

    raise NoInstallFoundError(tag=tag)
