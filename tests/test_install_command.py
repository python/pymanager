import json
import os
import pytest
import secrets
from pathlib import Path, PurePath

from manage import install_command as IC
from manage import installs


@pytest.fixture
def alias_checker(tmp_path):
    with AliasChecker(tmp_path) as checker:
        yield checker


class AliasChecker:
    class Cmd:
        global_dir = "out"
        launcher_exe = "launcher.txt"
        launcherw_exe = "launcherw.txt"
        default_platform = "-64"

        def __init__(self, platform=None):
            if platform:
                self.default_platform = platform


    def __init__(self, tmp_path):
        self.Cmd.global_dir = tmp_path / "out"
        self.Cmd.launcher_exe = tmp_path / "launcher.txt"
        self.Cmd.launcherw_exe = tmp_path / "launcherw.txt"
        self._expect_target = "target-" + secrets.token_hex(32)
        self._expect = {
            "-32": "-32-" + secrets.token_hex(32),
            "-64": "-64-" + secrets.token_hex(32),
            "-arm64": "-arm64-" + secrets.token_hex(32),
            "w-32": "w-32-" + secrets.token_hex(32),
            "w-64": "w-64-" + secrets.token_hex(32),
            "w-arm64": "w-arm64-" + secrets.token_hex(32),
        }
        for k, v in self._expect.items():
            (tmp_path / f"launcher{k}.txt").write_text(v)

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        pass

    def check(self, cmd, tag, name, expect, windowed=0):
        IC._write_alias(
            cmd,
            {"tag": tag},
            {"name": f"{name}.txt", "windowed": windowed},
            self._expect_target,
        )
        print(*cmd.global_dir.glob("*"), sep="\n")
        assert (cmd.global_dir / f"{name}.txt").is_file()
        assert (cmd.global_dir / f"{name}.txt.__target__").is_file()
        assert (cmd.global_dir / f"{name}.txt").read_text() == expect
        assert (cmd.global_dir / f"{name}.txt.__target__").read_text() == self._expect_target

    def check_32(self, cmd, tag, name):
        self.check(cmd, tag, name, self._expect["-32"])

    def check_w32(self, cmd, tag, name):
        self.check(cmd, tag, name, self._expect["w-32"], windowed=1)

    def check_64(self, cmd, tag, name):
        self.check(cmd, tag, name, self._expect["-64"])

    def check_w64(self, cmd, tag, name):
        self.check(cmd, tag, name, self._expect["w-64"], windowed=1)

    def check_arm64(self, cmd, tag, name):
        self.check(cmd, tag, name, self._expect["-arm64"])

    def check_warm64(self, cmd, tag, name):
        self.check(cmd, tag, name, self._expect["w-arm64"], windowed=1)


def test_write_alias_tag_with_platform(alias_checker):
    alias_checker.check_32(alias_checker.Cmd, "1.0-32", "testA")
    alias_checker.check_w32(alias_checker.Cmd, "1.0-32", "testB")
    alias_checker.check_64(alias_checker.Cmd, "1.0-64", "testC")
    alias_checker.check_w64(alias_checker.Cmd, "1.0-64", "testD")
    alias_checker.check_arm64(alias_checker.Cmd, "1.0-arm64", "testE")
    alias_checker.check_warm64(alias_checker.Cmd, "1.0-arm64", "testF")


def test_write_alias_default_platform(alias_checker):
    alias_checker.check_32(alias_checker.Cmd("-32"), "1.0", "testA")
    alias_checker.check_w32(alias_checker.Cmd("-32"), "1.0", "testB")
    alias_checker.check_64(alias_checker.Cmd, "1.0", "testC")
    alias_checker.check_w64(alias_checker.Cmd, "1.0", "testD")
    alias_checker.check_arm64(alias_checker.Cmd("-arm64"), "1.0", "testE")
    alias_checker.check_warm64(alias_checker.Cmd("-arm64"), "1.0", "testF")


def test_write_alias_fallback_platform(alias_checker):
    alias_checker.check_64(alias_checker.Cmd("-spam"), "1.0", "testA")
    alias_checker.check_w64(alias_checker.Cmd("-spam"), "1.0", "testB")


def test_print_cli_shortcuts(patched_installs, assert_log, monkeypatch, tmp_path):
    class Cmd:
        global_dir = Path(tmp_path)
        def get_installs(self):
            return installs.get_installs(None)

    (tmp_path / "fake.exe").write_bytes(b"")

    monkeypatch.setitem(os.environ, "PATH", f"{os.environ['PATH']};{Cmd.global_dir}")
    IC.print_cli_shortcuts(Cmd())
    assert_log(
        assert_log.skip_until("Installed %s", ["Python 2.0-64", PurePath("C:\\2.0-64")]),
        assert_log.skip_until("%s will be launched by %s", ["Python 1.0-64", "py1.0[-64].exe"]),
        ("%s will be launched by %s", ["Python 1.0-32", "py1.0-32.exe"]),
    )


def test_print_path_warning(patched_installs, assert_log, tmp_path):
    class Cmd:
        global_dir = Path(tmp_path)
        def get_installs(self):
            return installs.get_installs(None)

    (tmp_path / "fake.exe").write_bytes(b"")

    IC.print_cli_shortcuts(Cmd())
    assert_log(
        assert_log.skip_until(".*Global shortcuts directory is not on PATH")
    )


def test_merge_existing_index(tmp_path):
    # This function is for multiple downloaded index.jsons, so it merges based
    # on the url property, which should usually be a local file.
    existing = tmp_path / "index.json"
    with open(existing, "w", encoding="utf-8") as f:
        json.dump({"versions": [
            {"id": "test-1", "url": "test-file-1.zip"},
            {"id": "test-2", "url": "test-file-2.zip"},
            {"id": "test-3", "url": "test-file-3.zip"},
        ]}, f)

    new = [
        # Ensure new versions appear first
        {"id": "test-4", "url": "test-file-4.zip"},
        # Ensure matching ID doesn't result in overwrite
        {"id": "test-1", "url": "test-file-1b.zip"},
        # Ensure matching URL excludes original entry
        {"id": "test-2b", "url": "test-file-2.zip"},
    ]

    IC._merge_existing_index(new, existing)

    assert new == [
        {"id": "test-4", "url": "test-file-4.zip"},
        {"id": "test-1", "url": "test-file-1b.zip"},
        {"id": "test-2b", "url": "test-file-2.zip"},
        {"id": "test-1", "url": "test-file-1.zip"},
        {"id": "test-3", "url": "test-file-3.zip"},
    ]
