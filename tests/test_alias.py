import pytest
import secrets

from manage import aliasutils as AU
from manage.exceptions import NoLauncherTemplateError


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
        force = False

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
        AU._create_alias(
            cmd,
            name=name,
            plat=tag.rpartition("-")[2],
            target=self._expect_target,
            script_code=script_code,
            windowed=windowed,
        )
        print(*cmd.global_dir.glob("*"), sep="\n")
        assert (cmd.global_dir / f"{name}.exe").is_file()
        assert (cmd.global_dir / f"{name}.exe.__target__").is_file()
        assert (cmd.global_dir / f"{name}.exe").read_text() == expect
        assert (cmd.global_dir / f"{name}.exe.__target__").read_text() == self._expect_target
        if script_code:
            assert (cmd.global_dir / f"{name}.exe.__script__.py").is_file()
            assert (cmd.global_dir / f"{name}.exe.__script__.py").read_text() == script_code

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
    with pytest.raises(NoLauncherTemplateError):
        AU._create_alias(
            fake_config,
            name="test.exe",
            plat="-64",
            target=tmp_path / "target.exe",
        )
    assert_log(
        "Create %s for %s using %s, chosen by %s",
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
    AU._create_alias(
        fake_config,
        name="test.exe",
        target=tmp_path / "target.exe",
    )
    assert_log(
        "Create %s for %s",
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
    AU._create_alias(
        fake_config,
        name="test.exe",
        target=tmp_path / "target.exe",
        _link=fake_link
    )
    assert_log(
        "Create %s for %s",
        "Searching %s for suitable launcher to link",
        "No existing launcher available",
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
    AU._create_alias(
        fake_config,
        name="test.exe",
        target=tmp_path / "target.exe",
        _link=fake_link
    )
    assert_log(
        "Create %s for %s",
        ("Created %s as hard link to %s", ("test.exe", "actual_launcher.txt")),
        assert_log.end_of_log(),
    )


def test_write_alias_launcher_no_linking(fake_config, assert_log, tmp_path):
    fake_config.scratch = {
        "aliasutils.create_alias.launcher_remap": {"launcher.txt": tmp_path / "actual_launcher.txt"},
    }
    fake_config.launcher_exe = tmp_path / "launcher.txt"
    fake_config.launcher_exe.write_bytes(b'Arbitrary contents')
    (tmp_path / "actual_launcher.txt").write_bytes(b'Arbitrary contents')
    fake_config.default_platform = '-32'
    fake_config.global_dir = tmp_path / "bin"
    AU._create_alias(
        fake_config,
        name="test.exe",
        target=tmp_path / "target.exe",
        _link=None
    )
    assert_log(
        "Create %s for %s",
        ("Created %s as copy of %s", ("test.exe", "launcher.txt")),
        assert_log.end_of_log(),
    )


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


def test_scan_entrypoints(fake_config, tmp_path):
    fake_config.enable_entrypoints = True
    root = tmp_path / "test_install"
    site = root / "site-packages"
    A = site / "A.dist-info"
    A.mkdir(parents=True, exist_ok=True)
    (root / "target.exe").write_bytes(b"")
    (A / "entry_points.txt").write_text("""[console_scripts]
a = a:main

[gui_scripts]
aw = a:main
""")

    install = dict(
        prefix=root,
        id="test",
        default=1,
        alias=[dict(name="target", target="target.exe")],
        shortcuts=[dict(kind="site-dirs", dirs=["site-packages"])],
    )

    actual = list(AU.calculate_aliases(fake_config, install))

    assert ["target", "python", "pythonw", "a", "aw"] == [a.name for a in actual]
    assert [0, 0, 1, 0, 1] == [a.windowed for a in actual]
    assert [None, None, None, "a", "a"] == [a.mod for a in actual]
    assert [None, None, None, "main", "main"] == [a.func for a in actual]


def test_scan_entrypoints_disabled(fake_config, tmp_path):
    fake_config.enable_entrypoints = False
    root = tmp_path / "test_install"
    site = root / "site-packages"
    A = site / "A.dist-info"
    A.mkdir(parents=True, exist_ok=True)
    (root / "target.exe").write_bytes(b"")
    (A / "entry_points.txt").write_text("""[console_scripts]
a = a:main

[gui_scripts]
aw = a:main
""")

    install = dict(
        prefix=root,
        id="test",
        default=1,
        alias=[dict(name="target", target="target.exe")],
        shortcuts=[dict(kind="site-dirs", dirs=["site-packages"])],
    )

    actual = list(AU.calculate_aliases(fake_config, install))

    assert ["target", "python", "pythonw"] == [a.name for a in actual]
    assert [0, 0, 1] == [a.windowed for a in actual]
    assert [None, None, None] == [a.mod for a in actual]
    assert [None, None, None] == [a.func for a in actual]


def test_create_aliases(fake_config, tmp_path):
    target = tmp_path / "target.exe"
    target.write_bytes(b"")

    created = []
    # Full arguments copied from source to ensure callers only pass valid args
    def _on_create(cmd, *, name, target, plat=None, windowed=0, script_code=None, allow_link=True):
        created.append((name, windowed, script_code))

    aliases = [
        AU.AliasInfo(install=dict(prefix=tmp_path), name="a", target=target),
        AU.AliasInfo(install=dict(prefix=tmp_path), name="a.exe", target=target),
        AU.AliasInfo(install=dict(prefix=tmp_path), name="aw", windowed=1, target=target),
    ]

    AU.create_aliases(fake_config, aliases, _create_alias=_on_create)
    print(created)

    assert ["a", "aw"] == [a[0] for a in created]
    assert [0, 1] == [a[1] for a in created]
    assert [None, None] == [a[2] for a in created]


def test_cleanup_aliases(fake_config, tmp_path):
    target = tmp_path / "target.exe"
    target.write_bytes(b"")

    aliases = [
        AU.AliasInfo(install=dict(prefix=tmp_path), name="A", target=target),
        AU.AliasInfo(install=dict(prefix=tmp_path), name="B.exe", target=target),
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
    AU.cleanup_aliases(fake_config, preserve=aliases, _unlink_many=unlinked)
    assert set(f.name for f in unlinked) == set(["C.exe", "C.exe.__script__.py", "C.exe.__target__"])

    # Ensure we don't break if unlinking fails
    def unlink2(names):
        raise PermissionError("Simulated error")
    AU.cleanup_aliases(fake_config, preserve=aliases, _unlink_many=unlink2)

    # Ensure the actual unlink works
    AU.cleanup_aliases(fake_config, preserve=aliases)
    assert set(f.name for f in root.glob("*")) == set(files[:-3])
