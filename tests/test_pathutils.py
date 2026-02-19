import pytest

from manage.pathutils import Path, PurePath, relative_to

def test_path_match():
    p = Path("python3.12.exe")
    assert p.match("*.exe")
    assert p.match("python*")
    assert p.match("python*.exe")
    assert p.match("python3.12*.exe")
    assert p.match("*hon3.*")
    assert p.match("p*3.*.exe")

    assert not p.match("*.com")
    assert not p.match("example*")
    assert not p.match("example*.com")
    assert not p.match("*ple*")


def test_path_stem():
    p = Path("python3.12.exe")
    assert p.stem == "python3.12"
    assert p.suffix == ".exe"
    p = Path("python3.12")
    assert p.stem == "python3"
    assert p.suffix == ".12"
    p = Path("python3")
    assert p.stem == "python3"
    assert p.suffix == ""
    p = Path(".exe")
    assert p.stem == ""
    assert p.suffix == ".exe"


def test_path_relative_to():
    p = Path(r"C:\A\B\C\python.exe")
    actual = relative_to(p, r"C:\A\B\C")
    assert isinstance(actual, Path)
    assert str(actual) == "python.exe"
    actual = relative_to(p, "C:\\")
    assert isinstance(actual, Path)
    assert str(actual) == r"A\B\C\python.exe"
    actual = relative_to(str(p), r"C:\A\B")
    assert isinstance(actual, str)
    assert actual == r"C\python.exe"
    actual = relative_to(bytes(p), r"C:\A\B")
    assert isinstance(actual, bytes)
    assert actual == rb"C\python.exe"

    assert relative_to(p, r"C:\A\B\C\D") is p
    assert relative_to(p, None) is p
