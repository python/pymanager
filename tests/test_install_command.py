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
    IC._write_alias(
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
    IC._write_alias(
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
    IC._write_alias(
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
        "install_command._write_alias.launcher_remap": {"launcher.txt": tmp_path / "actual_launcher.txt"},
    }
    fake_config.launcher_exe = tmp_path / "launcher.txt"
    fake_config.launcher_exe.write_bytes(b'Arbitrary contents')
    (tmp_path / "actual_launcher.txt").write_bytes(b'Arbitrary contents')
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    IC._write_alias(
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


@pytest.mark.parametrize("default", [1, 0])
def test_write_alias_default(alias_checker, monkeypatch, tmp_path, default):
    prefix = Path(tmp_path) / "runtime"

    class Cmd:
        global_dir = Path(tmp_path) / "bin"
        launcher_exe = None
        scratch = {}
        def get_installs(self):
            return [
                {
                    "alias": [
                        {"name": "python3.exe", "target": "p.exe"},
                        {"name": "pythonw3.exe", "target": "pw.exe", "windowed": 1},
                    ],
                    "default": default,
                    "prefix": prefix,
                }
            ]

    prefix.mkdir(exist_ok=True, parents=True)
    (prefix / "p.exe").write_bytes(b"")
    (prefix / "pw.exe").write_bytes(b"")

    written = []
    def write_alias(*a):
        written.append(a)

    monkeypatch.setattr(IC, "_write_alias", write_alias)
    monkeypatch.setattr(IC, "SHORTCUT_HANDLERS", {})

    IC.update_all_shortcuts(Cmd())

    if default:
        # Main test: python.exe and pythonw.exe are added in automatically
        assert sorted(w[2]["name"] for w in written) == ["python.exe", "python3.exe", "pythonw.exe", "pythonw3.exe"]
    else:
        assert sorted(w[2]["name"] for w in written) == ["python3.exe", "pythonw3.exe"]
    # Ensure we still only have the two targets
    assert set(w[3].name for w in written) == {"p.exe", "pw.exe"}


def test_print_cli_shortcuts(patched_installs, assert_log, monkeypatch, tmp_path):
    class Cmd:
        scratch = {}
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
        scratch = {}
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


def test_merge_existing_index_not_found(tmp_path):
    existing = tmp_path / "index.json"
    try:
        existing.unlink()
    except FileNotFoundError:
        pass

    # Expect no failure and no change
    new = [1, 2, 3]
    IC._merge_existing_index(new, existing)
    assert new == [1, 2, 3]


def test_merge_existing_index_not_valid(tmp_path):
    existing = tmp_path / "index.json"
    with open(existing, "w", encoding="utf-8") as f:
        print("It's not a list of installs", file=f)
        print("But more importantly,", file=f)
        print("it's not valid JSON!", file=f)

    # Expect no failure and no change
    new = [1, 2, 3]
    IC._merge_existing_index(new, existing)
    assert new == [1, 2, 3]


def test_preserve_site(tmp_path):
    root = tmp_path / "root"
    preserved = tmp_path / "_root"
    site = root / "site-packages"
    not_site = root / "site-not-packages"
    A = site / "A"
    B = site / "B.txt"
    C = site / "C.txt"
    A.mkdir(parents=True, exist_ok=True)
    B.write_bytes(b"")
    C.write_bytes(b"original")

    class Cmd:
        preserve_site_on_upgrade = False
        force = False
        repair = False

    state = IC._preserve_site(Cmd, root)
    assert not state
    assert not preserved.exists()
    Cmd.preserve_site_on_upgrade = True
    Cmd.force = True
    state = IC._preserve_site(Cmd, root)
    assert not state
    assert not preserved.exists()
    Cmd.force = False
    Cmd.repair = True
    state = IC._preserve_site(Cmd, root)
    assert not state
    assert not preserved.exists()

    Cmd.repair = False
    state = IC._preserve_site(Cmd, root)
    assert state == [(site, preserved / "0"), (None, preserved)]
    assert preserved.is_dir()

    root.rename(root.parent / "ex_root_1")
    IC._restore_site(Cmd, state)
    assert root.is_dir()
    assert A.is_dir()
    assert B.is_file()
    assert C.is_file()
    assert b"original" == C.read_bytes()
    assert not preserved.exists()

    state = IC._preserve_site(Cmd, root)
    assert state == [(site, preserved / "0"), (None, preserved)]

    assert not C.exists()
    C.parent.mkdir(parents=True, exist_ok=True)
    C.write_bytes(b"updated")
    IC._restore_site(Cmd, state)
    assert A.is_dir()
    assert B.is_file()
    assert C.is_file()
    assert b"updated" == C.read_bytes()
    assert not preserved.exists()
