from .logging import LOGGER


class Version:
    TEXT_MAP = {
        "*": 0,
        "dev": 1,
        "a": 2,
        "b": 3,
        "c": 4,
        "rc": 4,
        "": 1000,
    }

    _TEXT_UNMAP = {v: k for k, v in TEXT_MAP.items()}
    _LEVELS = None

    # Versions with more fields than this will be truncated.
    MAX_FIELDS = 8

    def __new__(cls, s):
        if isinstance(s, cls):
            return s
        return object.__new__(cls)

    def __init__(self, s):
        import re
        if isinstance(s, Version):
            s = s.s
        if not Version._LEVELS:
            Version._LEVELS = "|".join(re.escape(k) for k in self.TEXT_MAP if k)
        m = re.match(
            r"^(?P<numbers>\d+(\.\d+)*)([\.\-]?(?P<level>" + Version._LEVELS + r")[\.]?(?P<serial>\d*))?$",
            s,
            re.I,
        )
        if not m:
            raise ValueError("Failed to parse version %s", s)
        bits = [int(v) for v in m.group("numbers").split(".")]
        try:
            dev = self.TEXT_MAP[(m.group("level") or "").lower()]
        except LookupError:
            dev = 0
            LOGGER.warn("Version %s has invalid development level specified which will be ignored", s)
        self.s = s
        if len(bits) > self.MAX_FIELDS:
            LOGGER.warn("Version %s is too long and will be truncated to %s for ordering purposes",
                s, ".".join(map(str, bits[:self.MAX_FIELDS])))
        self.sortkey = (
            *bits[:self.MAX_FIELDS],
            *([0] * (self.MAX_FIELDS - len(bits))),
            len(bits),  # for sort stability
            dev,
            int(m.group("serial") or 0)
        )
        # Omit len(bits) for our hash value
        self._hash = hash(self.sortkey[:-3] + self.sortkey[-2:])
        self.prefix_match = dev == self.TEXT_MAP["*"]
        self.prerelease_match = dev == self.TEXT_MAP["dev"]

    def __str__(self):
        return self.s

    def __repr__(self):
        return self.s

    def __hash__(self):
        return self._hash

    def _are_equal(self, other, prefix_match=None, other_prefix_match=None, prerelease_match=None):
        if other is None:
            return False
        if isinstance(other, str):
            return self.s.casefold() == other.casefold()
        if not isinstance(other, type(self)):
            return False
        k1 = self.sortkey[:-3]
        k2 = other.sortkey[:-3]
        assert len(k1) == len(k2)
        n1 = self.sortkey[-3]
        n2 = other.sortkey[-3]
        pre1 = self.sortkey[-2:]
        pre2 = other.sortkey[-2:]
        if prefix_match is None:
            prefix_match = self.prefix_match
        if other_prefix_match is None:
            other_prefix_match = other.prefix_match

        if prefix_match and other_prefix_match:
            # Use the shorter sort key to match
            n1 = n2 = min(n1, n2)
        elif prefix_match:
            # Use our length
            if n1 > n2:
                # Prefix is longer, so fail
                return False
            n2 = n1
        elif other_prefix_match:
            # Use other length
            if n2 > n1:
                # Prefix is longer, so fail
                return False
            n1 = n2
        else:
            # Use full length
            n1 = n2 = len(k1)
            # Check prerelease fields when not doing a prefix match
            if not (self.prerelease_match if prerelease_match is None else prerelease_match):
                # Prerelease values must match
                if pre1 != pre2:
                    return False

        return k1[:n1] == k2[:n2]

    def startswith(self, other):
        if not isinstance(other, type(self)):
            other = type(self)(other)
        return self._are_equal(other, other_prefix_match=True, prerelease_match=False)

    def above_lower_bound(self, other):
        if other is None:
            return True
        if self.sortkey[:other.sortkey[-3]] > other.sortkey[:other.sortkey[-3]]:
            return True
        # We can also be above the bound by matching it and being a later prerelease
        if self._are_equal(other, prerelease_match=True):
            return self.sortkey[-2:] > other.sortkey[-2:]
        return False

    def below_upper_bound(self, other):
        if other is None:
            return True
        if self.sortkey[:other.sortkey[-3]] < other.sortkey[:other.sortkey[-3]]:
            return True
        return False

    def __eq__(self, other):
        return self._are_equal(other)

    def __gt__(self, other):
        if other is None:
            return True
        if isinstance(other, str):
            other = type(self)(other)
        return self.sortkey > other.sortkey

    def __lt__(self, other):
        if other is None:
            return False
        if isinstance(other, str):
            other = type(self)(other)
        return self.sortkey < other.sortkey

    def __le__(self, other):
        return self < other or self == other

    def __ge__(self, other):
        return self > other or self == other

    @property
    def is_prerelease(self):
        return self.sortkey[-2] < self.TEXT_MAP[""]

    def to_python_style(self, n=3, with_dev=True):
        v = ".".join(str(i) for i in self.sortkey[:min(n, self.MAX_FIELDS)])
        if with_dev:
            try:
                dev = self._TEXT_UNMAP[self.sortkey[-2]]
                if dev:
                    v += f"{dev}{self.sortkey[-1]}"
            except LookupError:
                pass
        return v
