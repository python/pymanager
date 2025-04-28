"""Minimal reimplementations of Path and PurePath.

This is primarily focused on avoiding the expensive imports that come with
pathlib for functionality that we don't need. This module now gets loaded on
every Python launch through PyManager
"""
import os


class PurePath:
    def __init__(self, *parts):
        total = ""
        for p in parts:
            try:
                p = p.__fspath__().replace("/", "\\")
            except AttributeError:
                p = str(p).replace("/", "\\")
            p = p.replace("\\\\", "\\")
            if p == ".":
                continue
            if p.startswith(".\\"):
                p = p[2:]
            if total:
                total += "\\" + p
            else:
                total += p
        self._parent, _, self.name = total.rpartition("\\")
        self._p = total.rstrip("\\")

    def __fspath__(self):
        return self._p

    def __repr__(self):
        return self._p

    def __str__(self):
        return self._p

    def __hash__(self):
        return hash(self._p.casefold())

    def __bool__(self):
        return bool(self._p)

    @property
    def stem(self):
        return self.name.rpartition(".")[0]

    @property
    def suffix(self):
        return self.name.rpartition(".")[2]

    @property
    def parent(self):
        return type(self)(self._parent)

    @property
    def parts(self):
        drive, root, tail = os.path.splitroot(self._p)
        bits = []
        if drive or root:
            bits.append(drive + root)
        if tail:
            bits.extend(tail.split("\\"))
        while "." in bits:
            bits.remove(".")
        while ".." in bits:
            i = bits.index("..")
            bits.pop(i)
            bits.pop(i - 1)
        return bits

    def __truediv__(self, other):
        other = str(other)
        # Quick hack to hide leading ".\" on paths. We don't fully normalise
        # here because it can change the meaning of paths.
        while other.startswith(("./", ".\\")):
            other = other[2:]
        return type(self)(os.path.join(self._p, other))

    def __eq__(self, other):
        if isinstance(other, PurePath):
            return self._p.casefold() == other._p.casefold()
        return self._p.casefold() == str(other).casefold()

    def __ne__(self, other):
        if isinstance(other, PurePath):
            return self._p.casefold() != other._p.casefold()
        return self._p.casefold() != str(other).casefold()

    def with_name(self, name):
        return type(self)(os.path.join(self._parent, name))

    def with_suffix(self, suffix):
        if suffix and suffix[:1] != ".":
            suffix = f".{suffix}"
        return type(self)(os.path.join(self._parent, self.stem + suffix))

    def relative_to(self, base):
        base = PurePath(base).parts
        parts = self.parts
        if not all(x.casefold() == y.casefold() for x, y in zip(base, parts)):
            raise ValueError("path not relative to base")
        return type(self)("\\".join(parts[len(base):]))

    def as_uri(self):
        drive, root, tail = os.path.splitroot(self._p)
        if drive[1:2] == ":" and root:
            return "file:///" + self._p.replace("\\", "/")
        if drive[:2] == "\\\\":
            return "file:" + self._p.replace("\\", "/")
        return "file://" + self._p.replace("\\", "/")

    def full_match(self, pattern):
        return self.match(pattern, full_match=True)

    def match(self, pattern, full_match=False):
        p = str(pattern).casefold().replace("/", "\\")
        assert "?" not in p

        m = self._p if full_match or "\\" in p else self.name
        m = m.casefold()

        if "*" not in p:
            return m.casefold() == p

        allow_skip = False
        for bit in p.split("*"):
            if bit:
                if allow_skip:
                    allow_skip = False
                    try:
                        i = m.index(bit)
                    except ValueError:
                        return False
                    m = m[i + len(bit):]
                elif m.startswith(bit):
                    m = m[len(bit):]
                else:
                    return False
            else:
                allow_skip = True
        return True


class Path(PurePath):
    @classmethod
    def cwd(cls):
        return cls(os.getcwd())

    def absolute(self):
        return Path.cwd() / self

    def exists(self):
        return os.path.exists(self._p)

    def is_dir(self):
        return os.path.isdir(self._p)

    def is_file(self):
        return os.path.isfile(self._p)

    def iterdir(self):
        try:
            return (self / n for n in os.listdir(self._p))
        except FileNotFoundError:
            return ()

    def glob(self, pattern):
        return (f for f in self.iterdir() if f.match(pattern))

    def lstat(self):
        return os.lstat(self._p)

    def mkdir(self, mode=0o777, parents=False, exist_ok=False):
        try:
            os.mkdir(self._p, mode)
        except FileNotFoundError:
            if not parents or self.parent == self:
                raise
            self.parent.mkdir(parents=True, exist_ok=True)
            self.mkdir(mode, parents=False, exist_ok=exist_ok)
        except OSError:
            # Cannot rely on checking for EEXIST, since the operating system
            # could give priority to other errors like EACCES or EROFS
            if not exist_ok or not self.is_dir():
                raise

    def rename(self, new_name):
        os.rename(self._p, new_name)
        return self.parent / PurePath(new_name)

    def rmdir(self):
        os.rmdir(self._p)

    def unlink(self):
        os.unlink(self._p)

    def open(self, mode="r", encoding=None, errors=None):
        if "b" in mode:
            return open(self._p, mode)
        if not encoding:
            encoding = "utf-8-sig" if "r" in mode else "utf-8"
        return open(self._p, mode, encoding=encoding, errors=errors or "strict")

    def read_bytes(self):
        with open(self._p, "rb") as f:
            return f.read()

    def read_text(self, encoding="utf-8-sig", errors="strict"):
        with open(self._p, "r", encoding=encoding, errors=errors) as f:
            return f.read()

    def write_bytes(self, data):
        with open(self._p, "wb") as f:
            f.write(data)

    def write_text(self, text, encoding="utf-8", errors="strict"):
        with open(self._p, "w", encoding=encoding, errors=errors) as f:
            f.write(text)
