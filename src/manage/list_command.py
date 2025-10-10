import json

from . import logging
from .exceptions import ArgumentError

LOGGER = logging.LOGGER


def _format_alias(i, seen):
    from manage.installs import get_install_alias_names
    aliases = [a for a in i.get("alias", ()) if a["name"].casefold() not in seen]
    seen.update(a["name"].casefold() for a in aliases)

    include_w = LOGGER.would_log_to_console(logging.VERBOSE)
    names = get_install_alias_names(aliases, windowed=include_w)
    return ", ".join(names)


def _format_tag_with_co(cmd, i):
    t = i["tag"]
    # Show the default platform as optional when configured.
    if cmd and cmd.default_platform and t.endswith(cmd.default_platform):
        t = t.removesuffix(cmd.default_platform) + f"[{cmd.default_platform}]"
    if i["company"].casefold() in ("PythonCore".casefold(), "---", ""):
        return t
    return rf"{i['company']}\{t}"


def _ljust(s, n):
    if len(s) <= n:
        return s.ljust(n)
    return s[:n - 3] + "..."


def format_table(cmd, installs):
    "Lists as a user-friendly table"

    columns = {
        "tag-with-co": "Tag",
        "default-star": " ",
        "display-name": "Name",
        "company": "Managed By",
        "sort-version": "Version",
        "alias": "Alias",
    }
    seen_alias = set()
    installs = [{
        **i,
        "alias": _format_alias(i, seen_alias),
        "sort-version": str(i['sort-version']),
        "default-star": "",
        "tag-with-co": _format_tag_with_co(cmd, i),
    } for i in installs]

    for i in installs:
        if i.get("default"):
            i["default-star"] = "*"
            break

    cwidth = {k: len(v) for k, v in columns.items()}
    for i in installs:
        for k, v in i.items():
            try:
                cwidth[k] = max(cwidth[k], len(v))
            except LookupError:
                pass

    # Maximum column widths
    show_truncated_warning = False
    mwidth = {"company": 30, "tag-with-co": 30, "display-name": 60, "sort-version": 15, "alias": 50}
    for k in list(cwidth):
        try:
            if cwidth[k] > mwidth[k]:
                cwidth[k] = mwidth[k]
                show_truncated_warning = True
        except LookupError:
            pass

    while sum(cwidth.values()) > logging.CONSOLE_MAX_WIDTH:
        # TODO: Some kind of algorithm for reducing column widths to fit
        break

    LOGGER.print("!B!%s!W!", "  ".join(columns[c].ljust(cwidth[c]) for c in columns), always=True)

    any_shown = False
    for i in installs:
        if not i.get("unmanaged"):
            clr = "!G!" if i.get("default-star") else ""
            LOGGER.print(f"{clr}%s!W!", "  ".join(_ljust(i.get(c, ""), cwidth[c]) for c in columns), always=True)
            any_shown = True
    if not any_shown:
        LOGGER.print("!Y!-- No runtimes. Use 'py install <version>' to install one. --!W!")
    shown_header = False
    for i in installs:
        if i.get("unmanaged"):
            if not shown_header:
                LOGGER.print(always=True)
                LOGGER.print("!B!* These runtimes were found, but cannot be updated or uninstalled. *!W!", always=True)
                shown_header = True
            clr = "!G!" if i.get("default") else ""
            LOGGER.print(f"{clr}%s!W!", "  ".join(i.get(c, "").ljust(cwidth[c]) for c in columns), always=True)

    if show_truncated_warning:
        LOGGER.print()
        LOGGER.print("!B!Some columns were truncated. See '!G!py list --help!B!'"
                     " for alternative ways to display this information.!W!")


CSV_EXCLUDE = frozenset([
    "schema", "unmanaged",
    # Complex columns of limited value
    "install-for", "shortcuts", "__original-shortcuts",
    "executable", "executable_args",
])

CSV_EXPAND = frozenset(["run-for", "alias"])

def _csv_filter_and_expand(installs, *, exclude=CSV_EXCLUDE, expand=CSV_EXPAND):
    for i in installs:
        filtered = {}
        to_expand = {k: [] for k in expand}
        for k, v in i.items():
            if k in exclude:
                continue
            elif k in to_expand and isinstance(v, (list, tuple)):
                for vv in v:
                    try:
                        items = vv.items
                    except AttributeError:
                        expanded = {f"{k}": vv}
                    else:
                        expanded = {f"{k}.{k2}": vvv for k2, vvv in items()}
                    to_expand[k].append(expanded)
            else:
                filtered[k] = v

        any_yielded = False
        for k in expand:
            for expanded in to_expand[k]:
                yield filtered | expanded
                any_yielded = True
        if not any_yielded:
            yield filtered


def format_csv(cmd, installs):
    "List as a comma-separated value table"
    import csv
    installs = list(_csv_filter_and_expand(installs))
    if not installs:
        return
    columns = list(dict.fromkeys(col for i in installs for col in i))

    class LoggingIOWrapper:
        @staticmethod
        def write(s):
            LOGGER.print_raw(s, end="")

    writer = csv.DictWriter(LoggingIOWrapper, columns)
    writer.writeheader()
    writer.writerows(installs)


def format_json(cmd, installs):
    "Lists as a single JSON object"
    LOGGER.print_raw(json.dumps({"versions": installs}, default=str))


def format_json_lines(cmd, installs):
    "Lists as JSON on each line"
    for i in installs:
        LOGGER.print_raw(json.dumps(i, default=str))


def format_bare_id(cmd, installs):
    "Lists the runtime ID"
    for i in installs:
        # Don't print useless values (__active-virtual-env, __unmanaged-)
        if i["id"].startswith("__"):
            continue
        LOGGER.print_raw(i["id"])


def format_bare_exe(cmd, installs):
    "Lists the main executable path"
    for i in installs:
        LOGGER.print_raw(i["executable"])


def format_bare_prefix(cmd, installs):
    "Lists the prefix directory"
    for i in installs:
        try:
            LOGGER.print_raw(i["prefix"])
        except KeyError:
            pass


def format_bare_url(cmd, installs):
    "Lists the original source URL"
    for i in installs:
        try:
            LOGGER.print_raw(i["url"])
        except KeyError:
            pass


def list_formats(cmd, installs):
    "List the available list formats"
    max_key_width = len("Format")
    items = []
    for k, v in FORMATTERS.items():
        try:
            doc = v.__doc__.partition("\n")[0].strip()
        except AttributeError:
            doc = ""
        if len(k) > max_key_width:
            max_key_width = len(k)
        items.append((k, doc))
    LOGGER.print(f"!B!{'Format':<{max_key_width}} Description!W!", always=True)
    for k, doc in items:
        LOGGER.print(f"{k:<{max_key_width}} {doc}", always=True)


def format_legacy(cmd, installs, paths=False):
    "List runtimes using the old format"
    seen_default = False
    # TODO: Filter out unmanaged runtimes that have managed equivalents
    # The default order (which should be preserved) of 'installs' will put the
    # unmanaged runtimes first. So we can't just filter as we go, it needs to
    # be a separate pass. We should also reorder PythonCore prereleases above
    # non-PythonCore installs, since the Company will distinguish.
    # But legacy output is uninteresting, so it can be done later.
    for i in installs:
        if i["id"] == "__active-virtual-env":
            tag = "  *"
            seen_default = True
        else:
            tag = _format_tag_with_co(cmd, i)
            if tag:
                tag = f" -V:{tag}"
            if not seen_default and i.get("default"):
                tag = f"{tag} *"
                seen_default = True
        LOGGER.print_raw(tag.ljust(17), i["executable"] if paths else i["display-name"])


def format_legacy_paths(cmd, installs):
    "List runtime paths using the old format"
    return format_legacy(cmd, installs, paths=True)


FORMATTERS = {
    "table": format_table,
    "csv": format_csv,
    "json": format_json,
    "jsonl": format_json_lines,
    "id": format_bare_id,
    "exe": format_bare_exe,
    "prefix": format_bare_prefix,
    "url": format_bare_url,
    "legacy": format_legacy,
    "legacy-paths": format_legacy_paths,
    "formats": list_formats,
}


def _get_installs_from_index(indexes, filters):
    from .urlutils import sanitise_url

    installs = []
    seen_ids = set()

    for index in indexes:
        count = 0
        for i in index.find_all(filters, seen_ids=seen_ids, with_prerelease=True):
            installs.append(i)
            count += 1
        LOGGER.debug("Fetched %i installs from %s", count, sanitise_url(index.source_url))

    return installs


def execute(cmd):
    LOGGER.debug("BEGIN list_command.execute: %r", cmd.args)

    if cmd.formatter_callable:
        formatter = cmd.formatter_callable
    else:
        try:
            LOGGER.debug("Get formatter %s", cmd.format)
            formatter = FORMATTERS[cmd.format]
        except LookupError:
            formatters = FORMATTERS.keys() - {"legacy", "legacy-paths"}
            expect = ", ".join(sorted(formatters))
            raise ArgumentError(f"'{cmd.format}' is not a valid format; expected one of: {expect}") from None

    from .tagutils import tag_or_range, install_matches_any
    tags = []
    plat = None
    for arg in cmd.args:
        if arg.casefold() == "default".casefold():
            LOGGER.debug("Replacing 'default' with '%s'", cmd.default_tag)
            tags.append(tag_or_range(cmd.default_tag))
        else:
            try:
                tags.append(tag_or_range(arg))
                try:
                    if not plat:
                        plat = tags[-1].platform
                except AttributeError:
                    pass
            except ValueError as ex:
                LOGGER.warn("%s", ex)
    plat = plat or cmd.default_platform

    if cmd.source:
        from .indexutils import Index
        from .urlutils import IndexDownloader
        installs = []
        first_exc = None
        for source in [
            None if cmd.fallback_source_only else cmd.source,
            cmd.fallback_source,
        ]:
            if source:
                try:
                    installs = _get_installs_from_index(
                        IndexDownloader(source, Index),
                        tags,
                    )
                    break
                except OSError as ex:
                    if first_exc is None:
                        first_exc = ex
        if first_exc:
            raise SystemExit(1) from first_exc
        if cmd.one:
            # Pick the first non-prerelease that'll install for our platform
            best = [i for i in installs
                    if any(t.endswith(plat) for t in i.get("install-for", []))]
            for i in best:
                if not i["sort-version"].is_prerelease:
                    installs = [i]
                    break
            else:
                installs = best[:1] or installs
    elif cmd.install_dir:
        try:
            installs = cmd.get_installs(include_unmanaged=cmd.unmanaged)
        except OSError:
            LOGGER.debug("Unable to read installs", exc_info=True)
            installs = []

        if tags:
            LOGGER.debug("Filtering to following items")
            for t in tags:
                LOGGER.debug("* %r", t)
            installs = [i for i in installs if install_matches_any(i, tags, loose_company=True)]

        if not cmd.unmanaged:
            # Just in case any leak through (e.g. active venv)
            installs = [i for i in installs if not i.get("unmanaged")]
    else:
        raise ArgumentError("Configuration file does not specify install directory.")

    if cmd.one:
        installs = [i for i in installs if i.get("default")][:1] or installs[:1]
    formatter(cmd, installs)

    LOGGER.debug("END list_command.execute")
