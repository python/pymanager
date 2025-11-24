import json
import os
import pytest
import secrets
from pathlib import Path, PurePath

from manage import aliasutils as AU


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
            self.scratch = {}
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
        AU.create_alias(
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
    alias_checker.check_32(alias_checker.Cmd(), "1.0-32", "testA")
    alias_checker.check_w32(alias_checker.Cmd(), "1.0-32", "testB")
    alias_checker.check_64(alias_checker.Cmd(), "1.0-64", "testC")
    alias_checker.check_w64(alias_checker.Cmd(), "1.0-64", "testD")
    alias_checker.check_arm64(alias_checker.Cmd(), "1.0-arm64", "testE")
    alias_checker.check_warm64(alias_checker.Cmd(), "1.0-arm64", "testF")


def test_write_alias_default_platform(alias_checker):
    alias_checker.check_32(alias_checker.Cmd("-32"), "1.0", "testA")
    alias_checker.check_w32(alias_checker.Cmd("-32"), "1.0", "testB")
    alias_checker.check_64(alias_checker.Cmd(), "1.0", "testC")
    alias_checker.check_w64(alias_checker.Cmd(), "1.0", "testD")
    alias_checker.check_arm64(alias_checker.Cmd("-arm64"), "1.0", "testE")
    alias_checker.check_warm64(alias_checker.Cmd("-arm64"), "1.0", "testF")


def test_write_alias_fallback_platform(alias_checker):
    alias_checker.check_64(alias_checker.Cmd("-spam"), "1.0", "testA")
    alias_checker.check_w64(alias_checker.Cmd("-spam"), "1.0", "testB")


def test_write_alias_launcher_missing(fake_config, assert_log, tmp_path):
    fake_config.launcher_exe = tmp_path / "non-existent.exe"
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
    )
    assert_log(
        "Checking for launcher.*",
        "Checking for launcher.*",
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Skipping %s alias because the launcher template was not found.",
        assert_log.end_of_log(),
    )


def test_write_alias_launcher_unreadable(fake_config, assert_log, tmp_path):
    class FakeLauncherPath:
        stem = "test"
        suffix = ".exe"
        parent = tmp_path

        @staticmethod
        def is_file():
            return True

        @staticmethod
        def read_bytes():
            raise OSError("no reading for the test")

    fake_config.scratch = {}
    fake_config.launcher_exe = FakeLauncherPath
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
    )
    assert_log(
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Failed to read launcher template at %s\\.",
        "Failed to read %s",
        assert_log.end_of_log(),
    )


def test_write_alias_launcher_unlinkable(fake_config, assert_log, tmp_path):
    def fake_link(x, y):
        raise OSError("Error for testing")

    fake_config.scratch = {}
    fake_config.launcher_exe = tmp_path / "launcher.txt"
    fake_config.launcher_exe.write_bytes(b'Arbitrary contents')
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
        _link=fake_link
    )
    assert_log(
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Failed to create hard link.+",
        "Created %s as copy of %s",
        assert_log.end_of_log(),
    )


def test_write_alias_launcher_unlinkable_remap(fake_config, assert_log, tmp_path):
    # This is for the fairly expected case of the PyManager install being on one
    # drive, but the global commands directory being on another. In this
    # situation, we can't hard link directly into the app files, and will need
    # to copy. But we only need to copy once, so if a launcher_remap has been
    # set (in the current process), then we have an available copy already and
    # can link to that.

    def fake_link(x, y):
        if x.match("launcher.txt"):
            raise OSError(17, "Error for testing")

    fake_config.scratch = {
        "aliasutils.create_alias.launcher_remap": {"launcher.txt": tmp_path / "actual_launcher.txt"},
    }
    fake_config.launcher_exe = tmp_path / "launcher.txt"
    fake_config.launcher_exe.write_bytes(b'Arbitrary contents')
    (tmp_path / "actual_launcher.txt").write_bytes(b'Arbitrary contents')
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
        _link=fake_link
    )
    assert_log(
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Failed to create hard link.+",
        ("Created %s as hard link to %s", ("test.exe", "actual_launcher.txt")),
        assert_log.end_of_log(),
    )

