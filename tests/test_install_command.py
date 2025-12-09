import json
import os
import pytest
import secrets
from pathlib import Path, PurePath

from manage import install_command as IC
from manage import installs


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
    not_site.mkdir(parents=True, exist_ok=True)
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

    install = {
        "shortcuts": [
            {"kind": "site-dirs", "dirs": ["site-packages"]},
        ],
    }

    state = IC._preserve_site(Cmd, root, install)
    assert not state
    assert not preserved.exists()
    Cmd.preserve_site_on_upgrade = True
    Cmd.force = True
    state = IC._preserve_site(Cmd, root, install)
    assert not state
    assert not preserved.exists()
    Cmd.force = False
    Cmd.repair = True
    state = IC._preserve_site(Cmd, root, install)
    assert not state
    assert not preserved.exists()

    Cmd.repair = False
    state = IC._preserve_site(Cmd, root, install)
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

    state = IC._preserve_site(Cmd, root, install)
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


@pytest.mark.parametrize("default", [1, 0])
def test_write_alias_default(monkeypatch, tmp_path, default):
    prefix = Path(tmp_path) / "runtime"

    class Cmd:
        global_dir = Path(tmp_path) / "bin"
        launcher_exe = None
        scratch = {}
        enable_shortcut_kinds = disable_shortcut_kinds = None
        def get_installs(self):
            return [
                {
                    "id": "test",
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


    created = []

    class AliasUtils:
        import manage.aliasutils as AU
        calculate_aliases = staticmethod(AU.calculate_aliases)

        @staticmethod
        def create_aliases(cmd, aliases):
            created.extend(aliases)

        @staticmethod
        def cleanup_aliases(cmd, preserve):
            pass

    IC.update_all_shortcuts(Cmd(), _aliasutils=AliasUtils)

    if default:
        # Main test: python.exe and pythonw.exe are added in automatically
        assert sorted(a.name for a in created) == ["python", "python3.exe", "pythonw", "pythonw3.exe"]
    else:
        assert sorted(a.name for a in created) == ["python3.exe", "pythonw3.exe"]
    # Ensure we still only have the two targets
    assert set(a.target for a in created) == {"p.exe", "pw.exe"}


class InstallCommandTestCmd:
    def __init__(self, tmp_path, *args, **kwargs):
        self.args = args
        self.tags = None
        self.download_cache = {}
        self.scratch = {
            "install_command.download_cache": self.download_cache,
        }
        self.automatic = kwargs.get("automatic", False)
        self.by_id = kwargs.get("by_id", False)
        self.default_install_tag = kwargs.get("default_install_tag", "1")
        self.default_platform = kwargs.get("default_platform", "-32")
        self.default_tag = kwargs.get("default_tag", "1")
        self.download = kwargs.get("download")
        if self.download:
            self.download = tmp_path / self.download
        self.dry_run = kwargs.get("dry_run", True)
        self.fallback_source = kwargs.get("fallback_source")
        self.force = kwargs.get("force", True)
        self.from_script = kwargs.get("from_script")
        self.log_file = kwargs.get("log_file")
        self.refresh = kwargs.get("refresh", False)
        self.repair = kwargs.get("repair", False)
        self.shebang_can_run_anything = kwargs.get("shebang_can_run_anything", False)
        self.shebang_can_run_anything_silently = kwargs.get("shebang_can_run_anything_silently", False)
        self.source = kwargs.get("source", "http://example.com/index.json")
        self.target = kwargs.get("target")
        if self.target:
            self.target = tmp_path / self.target
        self.update = kwargs.get("update", False)
        self.virtual_env = kwargs.get("virtual_env")

        self.index_installs = [
            {
                "schema": 1,
                "id": "test-1.1-32",
                "sort-version": "1.1",
                "company": "Test",
                "tag": "1.1-32",
                "install-for": ["1", "1.1", "1.1-32"],
                "display-name": "Test 1.1 (32)",
                "executable": "test.exe",
                "url": "about:blank",
            },
            {
                "schema": 1,
                "id": "test-1.0-32",
                "sort-version": "1.0",
                "company": "Test",
                "tag": "1.0-32",
                "install-for": ["1", "1.0", "1.0-32"],
                "display-name": "Test 1.0 (32)",
                "executable": "test.exe",
                "url": "about:blank",
            },
        ]
        self.download_cache["http://example.com/index.json"] = json.dumps({
            "versions": self.index_installs,
        })
        self.installs = [{
            **self.index_installs[-1],
            "source": self.source,
            "prefix": tmp_path / "test-1.0-32",
        }]

    def get_log_file(self):
        return self.log_file

    def get_installs(self):
        return self.installs

    def get_install_to_run(self, tag):
        for i in self.installs:
            if i["tag"] == tag or f"{i['company']}/{i['tag']}" == tag:
                return i
        raise LookupError


def test_install_simple(tmp_path, assert_log):
    cmd = InstallCommandTestCmd(tmp_path, "1.1", force=False)

    IC.execute(cmd)
    assert_log(
        assert_log.skip_until("Searching for Python matching %s", ["1.1"]),
        assert_log.skip_until("Installing %s", ["Test 1.1 (32)"]),
        ("Tag: %s\\\\%s", ["Test", "1.1-32"]),
    )


def test_install_already_installed(tmp_path, assert_log):
    cmd = InstallCommandTestCmd(tmp_path, "1.0", force=False)

    IC.execute(cmd)
    assert_log(
        assert_log.skip_until("Searching for Python matching %s", ["1.0"]),
        assert_log.skip_until("%s is already installed", ["Test 1.0 (32)"]),
    )


def test_install_from_script(tmp_path, assert_log):
    cmd = InstallCommandTestCmd(tmp_path, from_script=tmp_path / "t.py")

    cmd.from_script.parent.mkdir(parents=True, exist_ok=True)
    cmd.from_script.write_text("#! python1.1.exe")

    IC.execute(cmd)
    assert_log(
        assert_log.skip_until("Searching for Python matching"),
        assert_log.skip_until("Installing %s", ["Test 1.1 (32)"]),
        ("Tag: %s\\\\%s", ["Test", "1.1-32"]),
    )
