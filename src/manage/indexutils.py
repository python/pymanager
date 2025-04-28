from .exceptions import InvalidFeedError
from .logging import LOGGER
from .tagutils import tag_or_range, install_matches_any
from .verutils import Version

SCHEMA = {
    "next": str,
    "versions": [
        {
            "schema": 1,
            # Unique ID used for install detection/side-by-sides
            "id": str,
            # Version used to sort installs. Also determines prerelease
            "sort-version": Version,
            # Company field
            "company": str,
            # Default tag, mainly for UI purposes. Must also be specified in
            # 'install-for' and 'run-for'.
            "tag": str,
            # List of tags to install this package for. Does not have to be
            # unique across all installs; the first match will be selected.
            "install-for": [str],
            # List of tags to run this package for. Does not have to be unique
            # across all installs; the first match will be selected.
            "run-for": [{"tag": str, "target": str, "args": [str], "windowed": int}],
            # List of global CLI aliases to create for this package. Does not
            # have to be unique across all installs; the first match will be
            # created.
            "alias": [{"name": str, "target": str, "windowed": int}],
            # List of other kinds of shortcuts to create.
            "shortcuts": [{"kind": str, ...: ...}],
            # Name to display in the UI
            "display-name": str,
            # [RESERVED] Install prefix. This will always be overwritten, so
            # don't specify it in the index.
            "prefix": None,
            # Default executable path (relative to prefix)
            "executable": str,
            # Optional arguments to launch the executable with
            # (inserted before any user-provided arguments)
            "executable_args": [str],
            # URL to download the package
            "url": str,
            # Optional set of hashes to validate the download
            "hash": {
                ...: str,
            },
        },
    ],
}


def _typename(t):
    if isinstance(t, type):
        return t.__name__
    if isinstance(t, tuple):
        return ", ".join(map(_typename, t))
    return type(t).__name__


def _schema_error(actual, expect, ctxt):
    return InvalidFeedError("Expected '{}' at {}; found '{}'".format(
        _typename(expect), ".".join(ctxt), _typename(actual),
    ))


# More specific for better internal handling. Users don't need to distinguish.
class InvalidFeedVersionError(InvalidFeedError):
    pass


def _version_error(actual, expect, ctxt):
    return InvalidFeedVersionError("Expected {} {}; found {}".format(
        ".".join(ctxt), expect, actual,
    ))


def _validate_one_dict_match(d, expect):
    if not isinstance(d, dict):
        return True
    if not isinstance(expect, dict):
        return True
    try:
        if expect["schema"] == d["schema"]:
            return True
    except KeyError:
        pass
    try:
        if expect["version"] == d["version"]:
            return True
    except KeyError:
        pass

    for k, v in expect.items():
        if isinstance(v, int) and d.get(k) != v:
            return False
    if ... not in expect:
        for k in d:
            if k not in expect:
                return False
    return True
    

def _validate_one_or_list(d, expects, ctxt):
    if not isinstance(d, list):
        d = [d]
    ctxt.append("[]")
    for i, e in enumerate(d):
        ctxt[-1] = f"[{i}]"
        for expect in expects:
            if _validate_one_dict_match(e, expect):
                yield _validate_one(e, expect, ctxt)
                break
        else:
            raise InvalidFeedError("No matching 'version' or 'schema' at {}".format(
                ".".join(ctxt)
            ))
    del ctxt[-1]


def _validate_one(d, expect, ctxt=None):
    if ctxt is None:
        ctxt = []
    if expect is None:
        raise InvalidFeedError("Unexpected key {}".format(".".join(ctxt)))
    if isinstance(expect, int):
        if d != expect:
            raise _version_error(d, expect, ctxt)
        return d
    if isinstance(expect, list):
        return list(_validate_one_or_list(d, expect, ctxt))
    if expect is ...:
        # Allow ... value for arbitrary value types
        return d
    if isinstance(d, dict):
        if isinstance(expect, dict):
            d2 = {}
            for k, v in d.items():
                ctxt.append(k)
                try:
                    expect2 = expect[k]
                except LookupError:
                    # Allow ... key for arbitrary key names
                    try:
                        expect2 = expect[...]
                    except LookupError:
                        raise InvalidFeedError("Unexpected key {}".format(".".join(ctxt))) from None
                d2[k] = _validate_one(v, expect2, ctxt)
                del ctxt[-1]
            return d2
        raise _schema_error(dict, expect, ctxt)
    if isinstance(expect, type) and isinstance(d, expect):
        return d
    try:
        return expect(d)
    except Exception as ex:
        raise _schema_error(d, expect, ctxt) from ex


def _patch_schema_1(source_url, v):
    try:
        url = v["url"]
    except LookupError:
        pass
    else:
        from .urlutils import urljoin
        if "://" not in url:
            v["url"] = urljoin(source_url, url, to_parent=True)

    # HACK: to help transition alpha users from their existing installs
    try:
        v["display-name"] = v["displayName"]
    except LookupError:
        pass

    return v


_SCHEMA_PATCHES = {
    1: _patch_schema_1,
}


def _patch(source_url, v):
    return _SCHEMA_PATCHES.get(v.get("schema"), lambda _, v: v)(source_url, v)


class Index:
    def __init__(self, source_url, d):
        try:
            validated = _validate_one(d, SCHEMA)
        except InvalidFeedError as ex:
            LOGGER.debug("ERROR:", exc_info=True)
            raise InvalidFeedError(feed_url=source_url) from ex
        self.source_url = source_url
        self.next_url = validated.get("next")
        versions = [_patch(source_url, v) for v in validated["versions"]]
        self.versions = sorted(versions, key=lambda v: v["sort-version"], reverse=True)

    def __repr__(self):
        return "<Index({!r}, next={!r}, versions=[...{} entries])>".format(
            self.source_url,
            self.next_url,
            len(self.versions),
        )

    def find_all(self, tags, *, seen_ids=None, loose_company=False, with_prerelease=False):
        filters = []
        for tag in tags:
            try:
                filters.append(tag_or_range(tag))
            except ValueError as ex:
                LOGGER.warn("%s", ex)
        for i in self.versions:
            if seen_ids is not None:
                if i["id"].casefold() in seen_ids:
                    continue
            if with_prerelease or not i["sort-version"].is_prerelease:
                if not filters or install_matches_any(i, filters, loose_company=loose_company):
                    if seen_ids is not None:
                        seen_ids.add(i["id"].casefold())
                    yield i

    def find_to_install(self, tag, *, loose_company=False, prefer_prerelease=False):
        tag_list = [tag] if tag else []
        LOGGER.debug("Finding %s to install", tag_list)
        for i in self.find_all(tag_list, loose_company=loose_company, with_prerelease=prefer_prerelease):
            return i
        if not loose_company:
            return self.find_to_install(tag, loose_company=True, prefer_prerelease=prefer_prerelease)
        if not prefer_prerelease:
            for i in self.find_all(tag_list, loose_company=loose_company, with_prerelease=True):
                return i
        LOGGER.debug("No install found for %s", tag_list)
        raise LookupError(tag)
