import pytest

import _native

from pathlib import Path


def test_simple_shortcut(tmp_path):
    open(tmp_path / "target.txt", "wb").close()
    _native.shortcut_create(
        tmp_path / "test.lnk",
        tmp_path / "target.txt",
    )
    assert (tmp_path / "test.lnk").is_file()



def test_start_path():
    p = Path(_native.shortcut_get_start_programs())
    assert p.is_dir()

    # Should be writable
    f = p / "__test_file.txt"
    try:
        open(f, "wb").close()
    finally:
        f.unlink()
