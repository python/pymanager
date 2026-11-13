from .verutils import Version

"""
Tags are our primary mechanism for letting users select an install.

At the simplest level, installs offer a list of tags, and if the user requests
one of those tags, the "best" install offering that tag is selected.

Tags are matched using the following logic:
* split at the last forward/backslash into company and tag parts
* if the tag part ends with a known platform tag, capture it and remove it
* split the tag part into segments at each hyphen
* if a segment starts with some kind of version number, the version number is
  parsed (including standard a#/b#/rc# prerelease suffixes) and the remainder is
  treated as text
* otherwise, treat the entire segment as text
* to be equal, two tags must have the same number of segments and they must
  all be equal, and the company parts should be equal (case-insensitive)
* to match, the company part should be a prefix
* versions are numeric and zero-padded to the same length, so '01.2'=='1.2.0.0'
* text is casefold()'d and must match exactly
* requested tags only have to match the leading segments of offerred tags, that
  is, if a user requests "a-b" and a package offers "a-b-c", it can match
* company parts are casefold()'d and prefix matched; in accordance with PEP 514,
  an empty company is treated as "PythonCore"
* platform tags are casefold()'d and must fully match. The default platform is
  handled by querying first with the default platform unconditionally appended,
  and retrying without if no matches are found.

When sorting tags, later versions sort above earlier versions, and text sorts
alphabetically.

For ordered constraints (e.g. '>=3.14t'), hyphen-separated segments are compared
from left to right. Text must match case-insensitively, including the text suffix
of a version segment. Versions are compared at the constraint's numeric precision,
zero-padding shorter versions. The first non-equal version determines the result,
and remaining segments are ignored. Missing segments or mismatching text before
that point fail the comparison.
This means constraints are not complementary - 'x>=y' is not equivalent to
'not(x<y)', e.g. '3.14t' satisfies neither '>=3.14' nor '<3.14'.

The logic for choosing the "best" install largely lives in installs.py and it
varies based on context. In brief:
* packages in an index are assumed to be ordered, and so the first one offering
  a matching 'install-for' tag is selected. It is up to the index to order
  entries according to their own policy
* installed packages are grouped by prerelease/non-prerelease 'sort-version',
  and then ordered by their primary 'tag' (and then 'sort-version' if needed).
  All prereleases follow the non-prereleases. The first package offering a
  matching 'run-for' tag after ordering is selected to launch/list/uninstall
* if the request tag has a text segment 'dev', then the grouping above is
  skipped, allowing prereleases to be selected over non-prereleases (note that
  the package must offer a tag containing 'dev' to be considered in this case)
* if a windowed launch is requested, installs that do not specifically offer one
  are skipped initially, but may be selected later if no runtime with windowed
  support is found
"""

# These suffixes on a tag get special treatment when it comes to ordering
# and matching. Must be a tuple in ascending sort order
SUPPORTED_PLATFORM_SUFFIXES = ("-64", "-32", "-arm64")


class _CompanyKey:
    CORE_COMPANY_NAMES = frozenset(map(str.casefold, ["CPython", "PythonCore", ""]))

    def __init__(self, company, allow_prefix=True):
        self.company = company or ""
        self._company = self.company.casefold()
        self.is_core = self._company in self.CORE_COMPANY_NAMES
        if self.is_core:
            self._company = ""
        self.allow_prefix = allow_prefix

    def startswith(self, other):
        if self.is_core and other.is_core:
            return True
        if self.allow_prefix:
            if self.is_core:
                return any(c.startswith(other._company) for c in self.CORE_COMPANY_NAMES)
            return self._company.startswith(other._company)
        return self._company == other._company

    def __hash__(self):
        return hash(self._company)

    def __eq__(self, other):
        return self._company == other._company

    def __ne__(self, other):
        return self._company != other._company

    def __lt__(self, other):
        if self.is_core and not other.is_core:
            return True
        if other.is_core:
            return False
        return self._company < other._company

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return not (self <= other)

    def __ge__(self, other):
        return not (self < other)


def companies_match(c1, c2):
    return _CompanyKey(c1) == _CompanyKey(c2)


class _AscendingText:
    def __init__(self, s):
        self.s = s.casefold()

    def compatible_with_bound(self, other):
        return type(self) is type(other) and self.s == other.s

    def startswith(self, other):
        return self == other

    def matches_bound(self, other):
        return self == other

    def above_lower_bound(self, other):
        if not isinstance(other, type(self)):
            return False
        if not other.s:
            return False
        return self.s > other.s

    def below_upper_bound(self, other):
        if not isinstance(other, type(self)):
            return False
        if not other.s:
            return False
        return self.s < other.s

    def __hash__(self):
        return hash(self.s)

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return self.s == other.s

    def __ne__(self, other):
        return not (self == other)

    def __lt__(self, other):
        if other is None:
            return False
        if not isinstance(other, type(self)):
            return False
        return self.s < other.s

    def __le__(self, other):
        return self == other or self < other

    def __gt__(self, other):
        return not (self <= other)

    def __ge__(self, other):
        return not (self < other)

    def __bool__(self):
        return bool(self.s)

    def __repr__(self):
        return repr(self.s)

    def __str__(self):
        return self.s


class DescendingVersion:
    """A version number with an optional text suffix, ordered descending.

    The suffix is the text immediately following the version in the same tag
    segment, e.g. 't' in '3.14t'. It must match exactly for any comparison.
    """
    def __init__(self, s, suffix=""):
        if isinstance(s, DescendingVersion):
            self.version = s.version
            self.suffix = suffix.casefold() if suffix else s.suffix
        else:
            self.version = Version(s)
            self.suffix = suffix.casefold()

    def compatible_with_bound(self, other):
        return isinstance(other, DescendingVersion) and self.suffix == other.suffix

    def startswith(self, other):
        if isinstance(other, str):
            other = DescendingVersion(other)
        if not isinstance(other, DescendingVersion) or self.suffix != other.suffix:
            return False
        return self.version.startswith(other.version)

    def matches_bound(self, other):
        if not isinstance(other, DescendingVersion) or self.suffix != other.suffix:
            return False
        k1, k2 = Version.get_comparable_tuples(self.version, other.version)
        return k1 == k2

    def above_lower_bound(self, other):
        if other is None:
            return True
        if not isinstance(other, DescendingVersion) or self.suffix != other.suffix:
            return False
        k1, k2 = Version.get_comparable_tuples(self.version, other.version)
        return k1 > k2

    def below_upper_bound(self, other):
        if other is None:
            return True
        if not isinstance(other, DescendingVersion) or self.suffix != other.suffix:
            return False
        k1, k2 = Version.get_comparable_tuples(self.version, other.version)
        return k1 < k2

    def __hash__(self):
        # Omit the field count, as with Version
        return hash((self.version.sortkey[:-1], self.suffix))

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        return (
            self.version.sortkey[:-1] == other.version.sortkey[:-1]
            and self.suffix == other.suffix
        )

    def __ne__(self, other):
        return not (self == other)

    def __str__(self):
        return str(self.version) + self.suffix

    def __repr__(self):
        return repr(str(self))

    def _less(self, other):
        # Versions descend, then suffixes ascend, then longer versions first
        k1 = self.version.sortkey
        k2 = other.version.sortkey
        if k1[:-1] != k2[:-1]:
            return k1[:-1] > k2[:-1]
        if self.suffix != other.suffix:
            return self.suffix < other.suffix
        return k1[-1] > k2[-1]

    def __gt__(self, other):
        if other is None:
            return True
        if not isinstance(other, DescendingVersion):
            if isinstance(other, str):
                other = DescendingVersion(other)
            else:
                return False
        return other._less(self)

    def __lt__(self, other):
        if other is None:
            return False
        if not isinstance(other, DescendingVersion):
            if isinstance(other, str):
                other = DescendingVersion(other)
            else:
                return True
        return self._less(other)

    def __le__(self, other):
        return self < other or self == other

    def __ge__(self, other):
        return self > other or self == other


def split_platform(tag):
    for t in SUPPORTED_PLATFORM_SUFFIXES:
        if tag[-len(t):].casefold() == t:
            return tag[:-len(t)], t
    return tag, ""


def _platform_gt(x, y):
    # This function is undefined if x == y
    assert x != y
    if not x:
        return False
    if not y:
        return True
    try:
        ix = SUPPORTED_PLATFORM_SUFFIXES.index(x)
    except ValueError:
        # if x is unknown, it comes after
        return True
    try:
        return ix > SUPPORTED_PLATFORM_SUFFIXES.index(y)
    except ValueError:
        # if y is unknown, x comes before it
        return False


def _sort_tag(tag):
    import re
    key = []

    if not tag:
        return ()

    for bit in tag.split("-"):
        m = re.match(r"^(\d+(?:\.\d+)*(?:(?:a|b|rc)\d+)?)(.*)$", bit, re.I)
        if m:
            key.append(DescendingVersion(m.group(1), m.group(2)))
        else:
            key.append(_AscendingText(bit))
    return tuple(key)


class CompanyTag:
    def __init__(self, company_or_tag, tag=None, *, loose_company=True):
        if isinstance(company_or_tag, str):
            if tag is not None:
                company = company_or_tag
            else:
                company, _, tag = (company_or_tag or "").replace("/", "\\").rpartition("\\")
            self._company = _CompanyKey(company, allow_prefix=loose_company)
        else:
            assert isinstance(company_or_tag, _CompanyKey)
            self._company = company_or_tag
        self.tag, self.platform = split_platform(tag)
        self._sortkey = _sort_tag(self.tag)
        self.prefers_prerelease = _AscendingText("dev") in self._sortkey

    @property
    def company(self):
        return self._company.company

    @property
    def is_core(self):
        return self._company.is_core

    def __add__(self, other):
        if isinstance(other, str):
            return type(self)(self._company, self.tag + self.platform + other)
        return NotImplemented

    def match(self, pattern):
        if isinstance(pattern, str):
            other = type(self)(pattern)
        else:
            other = pattern
        if not self._company.startswith(other._company):
            return False
        if len(self._sortkey) < len(other._sortkey):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if not x.startswith(y):
                return False
        if other.platform not in (self.platform, ""):
            return False
        return True

    def satisfied_by(self, tag):
        return tag.match(self)

    def __str__(self):
        if self.is_core:
            return f"{self.tag}{self.platform}"
        return f"{self.company}\\{self.tag}{self.platform}"

    def __repr__(self):
        return repr(str(self))

    def __hash__(self):
        return hash(self._sortkey)

    def __eq__(self, other):
        if not isinstance(other, type(self)):
            return False
        if self._company != other._company:
            return False
        if self._sortkey != other._sortkey:
            return False
        if self.platform != other.platform:
            return False
        return True

    def __gt__(self, other):
        if other is None:
            return True
        if not isinstance(other, type(self)):
            return False
        if self._company != other._company:
            return self._company > other._company
        if self._sortkey != other._sortkey:
            return self._sortkey > other._sortkey
        if self.platform != other.platform:
            return _platform_gt(self.platform, other.platform)
        return False

    def _compatible_with_bound(self, other):
        if not isinstance(other, type(self)):
            return False
        if not self._company.startswith(other._company):
            return False
        if other.platform not in (self.platform, ""):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if not x.compatible_with_bound(y):
                return False
            if not x.matches_bound(y):
                # First non-equal version decides (via the caller's bound
                # check); its suffix was already checked as compatible.
                return True
        return len(self._sortkey) >= len(other._sortkey)

    def matches_bound(self, other):
        if other is None:
            return True
        if not self._compatible_with_bound(other):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if not x.matches_bound(y):
                return False
        return True

    def above_lower_bound(self, other):
        if other is None:
            return True
        if not self._compatible_with_bound(other):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if x.above_lower_bound(y):
                return True
            if x.below_upper_bound(y):
                return False
        return False

    def __lt__(self, other):
        if not isinstance(other, type(self)):
            return False
        if self._company != other._company:
            return self._company < other._company
        if self._sortkey != other._sortkey:
            return self._sortkey < other._sortkey
        if self.platform != other.platform:
            return not _platform_gt(self.platform, other.platform)
        return False

    def below_upper_bound(self, other):
        if other is None:
            return True
        if not self._compatible_with_bound(other):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if x.above_lower_bound(y):
                return False
            if x.below_upper_bound(y):
                return True
        return False

    def __ge__(self, other):
        return self > other or self == other

    def __le__(self, other):
        return self < other or self == other


class TagRange:
    def __init__(self, spec):
        self.ranges = ranges = []
        for s in spec.replace(";", ",").split(","):
            s = s.strip()
            if not s:
                continue
            for r_cls in self.Range.__subclasses__():
                if s.startswith(r_cls.OP):
                    ranges.append(r_cls(s[len(r_cls.OP):].strip()))
                    break
            else:
                raise ValueError(f"Unsupported range specifier: '{s}'")

    def __repr__(self):
        return "<TagRange({})>".format(", ".join(repr(r) for r in self.ranges))

    @property
    def prefers_prerelease(self):
        return any(r.prefers_prerelease for r in self.ranges)

    def satisfied_by(self, tag):
        return all(r(tag) for r in self.ranges)

    def __add__(self, suffix):
        # This is probably a nonsense operation in general terms, but for the
        # simple cases of a single range it makes enough sense to allow it. The
        # alternative is probably to just crash, so we may as well not do that.
        r = type(self)("")
        r.ranges.extend(type(s)(s.tag + suffix) for s in self.ranges)
        return r

    class Range:
        def __init__(self, tag):
            if isinstance(tag, str):
                self.tag = CompanyTag(tag)
            else:
                assert isinstance(tag, CompanyTag)
                self.tag = tag

        @property
        def prefers_prerelease(self):
            return self.tag.prefers_prerelease

        def __repr__(self):
            return f"{self.OP}{self.tag}"

    class RangeEqual(Range):
        OP = "="
        def __call__(self, other):
            return other.matches_bound(self.tag)

    class RangeEqualEqual(Range):
        # Same as =, but provided for people who type it out of habit
        OP = "=="
        def __call__(self, other):
            return other.matches_bound(self.tag)

    class RangeRoughlyEqual(Range):
        # Same as =, but provided for people who type it out of habit
        OP = "~="
        def __call__(self, other):
            return other.matches_bound(self.tag)

    class RangeGreaterEqual(Range):
        OP = ">="
        def __call__(self, other):
            return other.matches_bound(self.tag) or other.above_lower_bound(self.tag)

    class RangeGreater(Range):
        OP = ">"
        def __call__(self, other):
            return other.above_lower_bound(self.tag)

    class RangeLessEqual(Range):
        OP = "<="
        def __call__(self, other):
            return other.matches_bound(self.tag) or other.below_upper_bound(self.tag)

    class RangeLess(Range):
        OP = "<"
        def __call__(self, other):
            return other.below_upper_bound(self.tag)

    class RangeExclude(Range):
        OP = "!="
        def __call__(self, other):
            return not other.matches_bound(self.tag)

        @property
        def prefers_prerelease(self):
            return False

def tag_or_range(tag):
    if not isinstance(tag, str):
        return tag
    tag = tag.lstrip(" =")
    if not tag:
        return CompanyTag("", "")
    if tag[:1] in "<>!":
        return TagRange(tag)
    if tag.lower() in ("default", "latest", "help"):
        raise ValueError(f"'{tag}' is not a valid tag or filter.")
    return CompanyTag(tag)


def install_matches_any(
    install,
    tags_or_ranges,
    *,
    loose_company=False,
    for_install=True,
    for_run=False,
):
    if not tags_or_ranges:
        return True

    if for_run:
        install_tags = [CompanyTag(install["company"], t["tag"], loose_company=loose_company)
                        for t in install.get("run-for", ())]
    elif for_install:
        install_tags = [CompanyTag(install["company"], t, loose_company=loose_company)
                        for t in install.get("install-for", ())]
    if not install_tags:
        install_tags.append(CompanyTag(install["company"], install["tag"],
                                       loose_company=loose_company))

    for f in tags_or_ranges:
        if not f:
            if install.get("default"):
                return True
            continue
        if any(f.satisfied_by(t) for t in install_tags):
            return True
    return False
