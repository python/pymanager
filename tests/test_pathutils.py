import pytest

from manage.pathutils import Path, PurePath

def test_path_match():
    p = Path("python3.12.exe")
    assert p.match("*.exe")
    assert p.match("python*")
    assert p.match("python*.exe")
    assert p.match("p*3.*.exe")
