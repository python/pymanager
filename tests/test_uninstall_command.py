import os
import pytest
import winreg

from pathlib import Path

from manage import uninstall_command as UC


def test_purge_global_dir(monkeypatch, registry, tmp_path):
    registry.setup(Path=rf"C:\A;{tmp_path}\X;{tmp_path};C:\B;%PTH%;C:\%D%\E")
    (tmp_path / "test.txt").write_bytes(b"")
    (tmp_path / "test2.txt").write_bytes(b"")

    monkeypatch.setitem(os.environ, "PTH", str(tmp_path))
    UC._do_purge_global_dir(tmp_path, "SLOW WARNING", hive=registry.hive, subkey=registry.root)
    assert registry.getvalueandkind("", "Path") == (
        rf"C:\A;{tmp_path}\X;C:\B;%PTH%;C:\%D%\E", winreg.REG_SZ)
    assert not list(tmp_path.iterdir())
