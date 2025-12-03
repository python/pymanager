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

    def check(self, cmd, tag, name, expect, windowed=0, script_code=None):
        created = set()
        AU.create_alias(
            cmd,
            {"tag": tag},
            {"name": name, "windowed": windowed},
            self._expect_target,
            created,
            script_code=script_code,
        )
        print(*cmd.global_dir.glob("*"), sep="\n")
        assert (cmd.global_dir / f"{name}.exe").is_file()
        assert (cmd.global_dir / f"{name}.exe.__target__").is_file()
        assert (cmd.global_dir / f"{name}.exe").read_text() == expect
        assert (cmd.global_dir / f"{name}.exe.__target__").read_text() == self._expect_target
        if script_code:
            assert (cmd.global_dir / f"{name}.exe.__script__.py").is_file()
            assert (cmd.global_dir / f"{name}.exe.__script__.py").read_text() == script_code
        assert name.casefold() in created

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

    def check_script(self, cmd, tag, name, windowed=0):
        self.check(cmd, tag, name, self._expect["w-32" if windowed else "-32"],
                   windowed=windowed, script_code=secrets.token_hex(128))


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


def test_write_script_alias(alias_checker):
    alias_checker.check_script(alias_checker.Cmd(), "1.0-32", "testA", windowed=0)
    alias_checker.check_script(alias_checker.Cmd(), "1.0-32", "testB", windowed=1)
    alias_checker.check_script(alias_checker.Cmd(), "1.0-32", "testA", windowed=0)


def test_write_alias_launcher_missing(fake_config, assert_log, tmp_path):
    fake_config.launcher_exe = tmp_path / "non-existent.exe"
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    created = set()
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
        created,
    )
    assert_log(
        "Checking for launcher.*",
        "Checking for launcher.*",
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Skipping %s alias because the launcher template was not found.",
        assert_log.end_of_log(),
    )
    assert "test".casefold() in created


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
    created = set()
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
        created,
    )
    assert_log(
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Failed to read launcher template at %s\\.",
        "Failed to read %s",
        assert_log.end_of_log(),
    )
    assert "test".casefold() in created


def test_write_alias_launcher_unlinkable(fake_config, assert_log, tmp_path):
    def fake_link(x, y):
        raise OSError("Error for testing")

    fake_config.scratch = {}
    fake_config.launcher_exe = tmp_path / "launcher.txt"
    fake_config.launcher_exe.write_bytes(b'Arbitrary contents')
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    created = set()
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
        created,
        _link=fake_link
    )
    assert_log(
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Failed to create hard link.+",
        "Created %s as copy of %s",
        assert_log.end_of_log(),
    )
    assert "test".casefold() in created


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
    created = set()
    AU.create_alias(
        fake_config,
        {"tag": "test"},
        {"name": "test.exe"},
        tmp_path / "target.exe",
        created,
        _link=fake_link
    )
    assert_log(
        "Checking for launcher.*",
        "Create %s linking to %s",
        "Failed to create hard link.+",
        ("Created %s as hard link to %s", ("test.exe", "actual_launcher.txt")),
        assert_log.end_of_log(),
    )
    assert "test".casefold() in created


def test_parse_entrypoint_line():
    for line, expect in [
        ("", (None, None, None)),
        ("# comment", (None, None, None)),
        ("name-only", (None, None, None)),
        ("name=value", (None, None, None)),
        ("name=mod:func", ("name", "mod", "func")),
        ("name=mod:func#comment", ("name", "mod", "func")),
        (" name = mod : func ", ("name", "mod", "func")),
        ("name=mod:func[extra]", ("name", "mod", "func")),
        ("name=mod:func [extra]", ("name", "mod", "func")),
    ]:
        assert expect == AU._parse_entrypoint_line(line)


def test_scan_create_entrypoints(fake_config, tmp_path):
    root = tmp_path / "test_install"
    site = root / "site-packages"
    A = site / "A.dist-info"
    A.mkdir(parents=True, exist_ok=True)
    (A / "entry_points.txt").write_text("""[console_scripts]
a = a:main

[gui_scripts]
aw = a:main
""")

    install = dict(prefix=root, id="test", alias=[dict(target="target.exe")])

    created = []
    AU.scan_and_create_entrypoints(
        fake_config,
        install,
        dict(dirs=["site-packages"]),
        set(),
        _create_alias=lambda *a, **kw: created.append((a, kw)),
    )
    assert 2 == len(created)
    for name, windowed, c in zip("a aw".split(), [0, 1], created):
        expect = dict(zip("cmd install alias target".split(), c[0])) | c[1]
        assert expect["cmd"] is fake_config
        assert expect["install"] is install
        assert expect["alias"]["name"] == name
        assert expect["alias"]["windowed"] == windowed
        assert expect["target"].match("target.exe")
        assert "from a import main" in expect["script_code"]


@pytest.mark.parametrize("alias_set", ["none", "one", "onew", "two"])
def test_scan_create_entrypoints_with_alias(fake_config, tmp_path, alias_set):
    # In this test, we fake the scan, but vary the set of aliases associated
    # with the installed runtime.
    # If there are no aliases, we shouldn't create any entrypoints.
    # If we have a non-windowed alias, we'll use that for both.
    # If we have a windowed alias, we'll only create windowed entrypoints.
    # If we have both, we'll use the appropriate one

    def fake_scan(*a):
        return [(dict(name="a", windowed=0), "CODE"),
                (dict(name="aw", windowed=1), "CODE")]

    alias = {
        "none": [],
        "one": [dict(target="test.exe", windowed=0)],
        "onew": [dict(target="testw.exe", windowed=1)],
        "two": [dict(target="test.exe", windowed=0),
                dict(target="testw.exe", windowed=1)],
    }[alias_set]

    expect = {
        "none": [],
        "one": [("a", "test.exe"), ("aw", "test.exe")],
        "onew": [("aw", "testw.exe")],
        "two": [("a", "test.exe"), ("aw", "testw.exe")],
    }[alias_set]

    created = []
    AU.scan_and_create_entrypoints(
        fake_config,
        dict(prefix=fake_config.root, id="test", alias=alias),
        {},
        set(),
        _create_alias=lambda *a, **kw: created.append((a, kw)),
        _scan=fake_scan,
    )
    names = [(c[0][2]["name"], c[0][3].name) for c in created]
    assert names == expect


def test_scan_entrypoints(tmp_path):
    site = tmp_path / "site"
    A = site / "a.dist-info"
    B = site / "b.dist-info"
    A.mkdir(exist_ok=True, parents=True)
    B.mkdir(exist_ok=True, parents=True)
    (A / "entry_points.txt").write_text("""# Test entries
[console_scripts]
a_cmd = a:main
a2_cmd = a:main2 [spam]

[other] # shouldn't be included
a3_cmd = a:main3

[gui_scripts]
aw_cmd = a:main
""")
    (B / "entry_points.txt").write_bytes(b"""# Invalid file

\x80\x81\x82\x83\x84\x85\x86\x87\x88\x89

[console_scripts]
b_cmd = b:main
""")
    actual = list(AU._scan_one(site))
    assert [a[0]["name"] for a in actual] == [
        "a_cmd", "a2_cmd", "aw_cmd"
    ]
    assert [a[0]["windowed"] for a in actual] == [0, 0, 1]
    assert [a[1].rpartition("sys.exit")[2].strip() for a in actual] == [
        "(main())", "(main2())", "(main())"
    ]


def test_cleanup_aliases(fake_config):
    fake_config.installs = [
        dict(id="A", alias=[dict(name="A", target="a.exe")], prefix=fake_config.global_dir),
    ]

    def fake_scan(*a):
        yield dict(name="B"), "CODE"

    # install/shortcut pairs are irrelevant, since we fake the scan entirely.
    # It just can't be empty or the scan is skipped.
    pairs = [
        (fake_config.installs[0], dict(kind="site-dirs", dirs=[])),
    ]

    root = fake_config.global_dir
    root.mkdir(parents=True, exist_ok=True)
    files = ["A.exe", "A.exe.__target__",
             "B.exe", "B.exe.__script__.py", "B.exe.__target__",
             "C.exe", "C.exe.__script__.py", "C.exe.__target__"]
    for f in files:
        (root / f).write_bytes(b"")

    # Ensure the expect files get requested to be unlinked
    class Unlinker(list):
        def __call__(self, names):
            self.extend(names)

    unlinked = Unlinker()
    AU.cleanup_alias(fake_config, pairs, _unlink_many=unlinked, _scan=fake_scan)
    assert set(f.name for f in unlinked) == set(["C.exe", "C.exe.__script__.py", "C.exe.__target__"])

    # Ensure we don't break if unlinking fails
    def unlink2(names):
        raise PermissionError("Simulated error")
    AU.cleanup_alias(fake_config, pairs, _unlink_many=unlink2, _scan=fake_scan)

    # Ensure the actual unlink works
    AU.cleanup_alias(fake_config, pairs, _scan=fake_scan)
    assert set(f.name for f in root.glob("*")) == set(files[:-3])
