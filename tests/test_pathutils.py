import pytest

from manage.pathutils import Path, PurePath

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
