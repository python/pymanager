import json
import sys

from .exceptions import ArgumentError
from .logging import LOGGER


def _exe_partition(n):
    n1, sep, n2 = n.rpartition(".")
    n2 = sep + n2
    while n1 and n1[-1] in "0123456789.-":
        n2 = n1[-1] + n2
        n1 = n1[:-1]
    w = ""
    if n1 and n1[-1] == "w":
        w = "w"
        n1 = n1[:-1]
    return n1, w, n2


def _format_alias(i, seen):
    try:
        alias = i["alias"]
    except KeyError:
        return ""
    if not alias:
        return ""
    if len(alias) == 1:
        a = i["alias"][0]
        n = a["name"].casefold()
        if n in seen:
            return ""
        seen.add(n)
        return i["alias"][0]["name"]
    names = {_exe_partition(a["name"].casefold()): a["name"] for a in alias
             if a["name"].casefold() not in seen}
    seen.update(a["name"].casefold() for a in alias)
    for n1, w, n2 in list(names):
        k = (n1, "", n2)
        if w and k in names:
            del names[n1, w, n2]
            n1, _, n2 = _exe_partition(names[k])
            names[k] = f"{n1}[w]{n2}"
    return ", ".join(names[n] for n in sorted(names))


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
        LOGGER.print("!B!Some columns were truncated. Use '!G!--format=json!B!'"
                     " or '!G!--format=jsonl!B!' for full information.!W!")


CSV_EXCLUDE = {
    "schema", "unmanaged",
    # Complex columns of limited value
    "install-for", "shortcuts", "__original-shortcuts",
    "executable", "executable_args",
}

CSV_EXPAND = ["run-for", "alias"]

def _csv_filter_and_expand(installs):
    for i in installs:
        i = {k: v for k, v in i.items() if k not in CSV_EXCLUDE}
        to_expand = {k: i.pop(k, ()) for k in CSV_EXPAND}
        yield i
        for k2, vlist in to_expand.items():
            for vv in vlist:
                yield {f"{k2}.{k}": v for k, v in vv.items()}


def format_csv(cmd, installs):
    import csv
    installs = list(_csv_filter_and_expand(installs))
    if not installs:
        return
    s = set()
    columns = [c for i in installs for c in i
               if c not in s and (s.add(c) or True)]
    writer = csv.DictWriter(sys.stdout, columns)
    writer.writeheader()
    writer.writerows(installs)


def format_json(cmd, installs):
    print(json.dumps({"versions": installs}, default=str))


def format_json_lines(cmd, installs):
    for i in installs:
        print(json.dumps(i, default=str))


def format_bare_id(cmd, installs):
    for i in installs:
        print(i["id"])


def format_bare_exe(cmd, installs):
    for i in installs:
        print(i["executable"])


def format_bare_prefix(cmd, installs):
    for i in installs:
        try:
            print(i["prefix"])
        except KeyError:
            pass


def format_bare_url(cmd, installs):
    for i in installs:
        print(i["url"])


def format_legacy(cmd, installs, paths=False):
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
        print(tag.ljust(17), i["executable"] if paths else i["display-name"])


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
    "legacy-paths": lambda cmd, i: format_legacy(cmd, i, paths=True),
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

    try:
        LOGGER.debug("Get formatter %s", cmd.format)
        formatter = FORMATTERS[cmd.format]
    except LookupError:
        formatters = FORMATTERS.keys() - {"legacy", "legacy-paths"}
        expect = ", ".join(sorted(formatters))
        raise ArgumentError(f"'{cmd.format}' is not a valid format; expect one of: {expect}") from None

    from .tagutils import tag_or_range, install_matches_any
    tags = []
    for arg in cmd.args:
        if arg.casefold() == "default".casefold():
            LOGGER.debug("Replacing 'default' with '%s'", cmd.default_tag)
            tags.append(tag_or_range(cmd.default_tag))
        else:
            try:
                tags.append(tag_or_range(arg))
            except ValueError as ex:
                LOGGER.warn("%s", ex)

    if cmd.source:
        from .indexutils import Index
        from .urlutils import IndexDownloader
        try:
            installs = _get_installs_from_index(
                IndexDownloader(cmd.source, Index),
                tags,
            )
        except OSError as ex:
            raise SystemExit(1) from ex
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
