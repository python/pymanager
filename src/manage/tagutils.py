from .verutils import Version


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

    def startswith(self, other):
        if not isinstance(other, type(self)):
            return False
        if not other.s:
            return not self.s
        return self.s.startswith(other.s)

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

    def __repr__(self):
        return repr(self.s)

    def __str__(self):
        return self.s


class _DescendingVersion(Version):
    def __gt__(self, other):
        if other is None:
            return True
        if not isinstance(other, type(self)):
            if isinstance(other, str):
                other = type(self)(other)
            else:
                return False
        return self.sortkey < other.sortkey

    def __lt__(self, other):
        if other is None:
            return False
        if not isinstance(other, type(self)):
            if isinstance(other, str):
                other = type(self)(other)
            else:
                return True
        return self.sortkey > other.sortkey


def _split_platform(tag):
    if tag.endswith(SUPPORTED_PLATFORM_SUFFIXES):
        for t in SUPPORTED_PLATFORM_SUFFIXES:
            if tag.endswith(t):
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
        m = re.match(r"^(\d+(?:\.\d+)*)(.*)$", bit)
        if m:
            key.append(_DescendingVersion(m.group(1)))
            key.append(_AscendingText(m.group(2)))
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
        self.tag, self.platform = _split_platform(tag)
        self._sortkey = _sort_tag(self.tag)

    @property
    def company(self):
        return self._company.company

    @property
    def is_core(self):
        return self._company.is_core

    def __add__(self, other):
        if isinstance(other, str):
            return type(self)(self._company, self.tag + other)
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

    def matches_bound(self, other):
        if other is None:
            return True
        if not isinstance(other, type(self)):
            return False
        if not self._company.startswith(other._company):
            return False
        if other.platform not in (self.platform, ""):
            return False
        if len(self._sortkey) < len(other._sortkey):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if isinstance(x, Version):
                if not x.startswith(y):
                    return False
            elif x != y:
                return False
        return True

    def above_lower_bound(self, other):
        if other is None:
            return True
        if not isinstance(other, type(self)):
            return False
        if not self._company.startswith(other._company):
            return False
        if other.platform not in (self.platform, ""):
            return False
        if len(self._sortkey) < len(other._sortkey):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if isinstance(x, Version):
                if not x.above_lower_bound(y):
                    return False
            elif x != y:
                return False
        return True

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
        if not isinstance(other, type(self)):
            return False
        if not self._company.startswith(other._company):
            return False
        if other.platform not in (self.platform, ""):
            return False
        if len(self._sortkey) > len(other._sortkey):
            return False
        for x, y in zip(self._sortkey, other._sortkey):
            if isinstance(x, Version):
                if not x.below_upper_bound(y):
                    return False
            elif x != y:
                return False
        return True

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


def install_matches_any(install, tags_or_ranges, *, loose_company=False):
    if not tags_or_ranges:
        return True

    own_tag = CompanyTag(install["company"], install["tag"], loose_company=loose_company)
    install_tags = [CompanyTag(install["company"], t, loose_company=loose_company)
                    for t in install.get("install-for", ())]
    if not install_tags:
        install_tags.append(own_tag)

    for f in tags_or_ranges:
        if not f:
            if install.get("default"):
                return True
            continue
        if isinstance(f, TagRange):
            if f.satisfied_by(own_tag):
                return True
        else:
            if any(f.satisfied_by(t) for t in install_tags):
                return True
    return False
