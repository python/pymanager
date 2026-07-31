import os
import pytest
import winreg

from pathlib import Path

from manage import uninstall_command as UC
from manage.exceptions import FilesInUseError


def test_purge_global_dir(monkeypatch, registry, tmp_path):
    registry.setup(Path=rf"C:\A;{tmp_path}\X;{tmp_path};C:\B;%PTH%;C:\%D%\E")
    (tmp_path / "test.txt").write_bytes(b"")
    (tmp_path / "test2.txt").write_bytes(b"")

    monkeypatch.setitem(os.environ, "PTH", str(tmp_path))
    UC._do_purge_global_dir(tmp_path, "SLOW WARNING", hive=registry.hive, subkey=registry.root)
    assert registry.getvalueandkind("", "Path") == (
        rf"C:\A;{tmp_path}\X;C:\B;%PTH%;C:\%D%\E", winreg.REG_SZ)
    assert not tmp_path.is_dir() or not list(tmp_path.iterdir())


def test_null_purge(fake_config):
    cmd = fake_config
    cmd.args = ["--purge"]
    cmd.confirm = False
    cmd.purge = True
    UC.execute(cmd)


def test_purge_unknown_files(fake_config):
    cmd = fake_config
    cmd.args = ["--purge"]
    cmd.confirm = False
    cmd.purge = True

    unknown_file = cmd.install_dir / "unknown.txt"
    unknown_file.write_bytes(b"unknown")
    broken_runtime = cmd.install_dir / "broken-runtime"
    broken_runtime.mkdir()
    (broken_runtime / "__install__.json").write_text("invalid")

    UC.execute(cmd)

    assert not unknown_file.exists()
    assert not broken_runtime.exists()


def test_purge_preserves_runtime_in_use(fake_config, monkeypatch):
    cmd = fake_config
    cmd.args = ["--purge"]
    cmd.confirm = False
    cmd.purge = True

    runtime = cmd.install_dir / "runtime"
    runtime.mkdir()
    executable = runtime / "python.exe"
    executable.write_bytes(b"in use")
    cmd.installs = [{
        "display-name": "Runtime in use",
        "prefix": runtime,
    }]

    unknown_dir = cmd.install_dir / "unknown"
    unknown_dir.mkdir()
    (unknown_dir / "file.txt").write_bytes(b"unknown")

    rmtree = UC.rmtree

    def locked_rmtree(path, *args, **kwargs):
        if Path(path) == runtime:
            raise FilesInUseError([executable])
        return rmtree(path, *args, **kwargs)

    monkeypatch.setattr(UC, "rmtree", locked_rmtree)

    UC.execute(cmd)

    assert executable.is_file()
    assert not unknown_dir.exists()
