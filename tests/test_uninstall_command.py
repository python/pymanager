import os
import pytest
import winreg

from pathlib import Path

from manage import uninstall_command as UC
from manage.exceptions import ArgumentError, FilesInUseError


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
    cmd.args = []
    cmd.confirm = False
    cmd.purge = True
    cmd.cleanup = False
    UC.execute(cmd)


def test_purge_unknown_files(fake_config):
    cmd = fake_config
    cmd.args = []
    cmd.confirm = False
    cmd.purge = True
    cmd.cleanup = False

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
    cmd.args = []
    cmd.confirm = False
    cmd.purge = True
    cmd.cleanup = False

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


def test_cleanup_preserves_recognized_runtimes(fake_config, monkeypatch):
    cmd = fake_config
    cmd.args = []
    cmd.purge = False
    cmd.cleanup = True

    runtime = cmd.install_dir / "runtime"
    runtime.mkdir()
    executable = runtime / "python.exe"
    executable.write_bytes(b"preserve")
    cmd.installs = [{
        "display-name": "Recognized runtime",
        "prefix": runtime,
    }]

    cmd.download_dir.mkdir()
    cached_file = cmd.download_dir / "cached.zip"
    cached_file.write_bytes(b"cached")
    unknown_file = cmd.install_dir / "unknown.txt"
    unknown_file.write_bytes(b"unknown")
    broken_runtime = cmd.install_dir / "broken-runtime"
    broken_runtime.mkdir()
    (broken_runtime / "__install__.json").write_text("invalid")

    prompts = []
    cmd.ask_yn = lambda prompt: prompts.append(prompt) or True
    refreshed = []
    monkeypatch.setattr(UC, "update_all_shortcuts", refreshed.append)

    UC.execute(cmd)

    assert prompts == [
        "Clean up cached files and unrecognized content? "
        "This will preserve recognized runtimes."
    ]
    assert executable.read_bytes() == b"preserve"
    assert not cmd.download_dir.exists()
    assert not unknown_file.exists()
    assert not broken_runtime.exists()
    assert refreshed == [cmd]


def test_cleanup_shared_download_dir_preserves_recognized_runtimes(
    fake_config, monkeypatch
):
    cmd = fake_config
    cmd.args = []
    cmd.purge = False
    cmd.cleanup = True
    cmd.download_dir = cmd.install_dir

    runtime = cmd.install_dir / "runtime"
    runtime.mkdir()
    executable = runtime / "python.exe"
    executable.write_bytes(b"preserve")
    cmd.installs = [{
        "display-name": "Recognized runtime",
        "prefix": runtime,
    }]

    cached_file = cmd.download_dir / "cached.zip"
    cached_file.write_bytes(b"cached")
    unknown_dir = cmd.install_dir / "unknown"
    unknown_dir.mkdir()

    cmd.ask_yn = lambda prompt: True
    refreshed = []
    monkeypatch.setattr(UC, "update_all_shortcuts", refreshed.append)

    UC.execute(cmd)

    assert executable.read_bytes() == b"preserve"
    assert not cached_file.exists()
    assert not unknown_dir.exists()
    assert refreshed == [cmd]


def test_cleanup_declined_preserves_all_files(fake_config, monkeypatch):
    cmd = fake_config
    cmd.args = []
    cmd.purge = False
    cmd.cleanup = True

    cmd.download_dir.mkdir()
    cached_file = cmd.download_dir / "cached.zip"
    cached_file.write_bytes(b"cached")
    unknown_file = cmd.install_dir / "unknown.txt"
    unknown_file.write_bytes(b"unknown")

    prompts = []
    cmd.ask_yn = lambda prompt: prompts.append(prompt) or False
    monkeypatch.setattr(
        UC,
        "update_all_shortcuts",
        lambda cmd: pytest.fail("shortcuts refreshed after cleanup was declined"),
    )

    UC.execute(cmd)

    assert prompts == [
        "Clean up cached files and unrecognized content? "
        "This will preserve recognized runtimes."
    ]
    assert cached_file.read_bytes() == b"cached"
    assert unknown_file.read_bytes() == b"unknown"


@pytest.mark.parametrize("option", ["purge", "cleanup"])
def test_global_uninstall_options_reject_tags(fake_config, option):
    cmd = fake_config
    cmd.args = ["3.14"]
    cmd.purge = option == "purge"
    cmd.cleanup = option == "cleanup"

    with pytest.raises(ArgumentError, match="does not accept runtime tags"):
        UC.execute(cmd)


def test_purge_and_cleanup_are_mutually_exclusive(fake_config):
    cmd = fake_config
    cmd.args = []
    cmd.purge = True
    cmd.cleanup = True

    with pytest.raises(ArgumentError, match="cannot be combined"):
        UC.execute(cmd)
