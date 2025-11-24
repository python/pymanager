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
    def create_alias(*a):
        written.append(a)

    monkeypatch.setattr(IC, "SHORTCUT_HANDLERS", {
        "site-dirs": (lambda *a: None,) * 2,
    })

    IC.update_all_shortcuts(Cmd(), _create_alias=create_alias)

    if default:
        # Main test: python.exe and pythonw.exe are added in automatically
        assert sorted(w[2]["name"] for w in written) == ["python.exe", "python3.exe", "pythonw.exe", "pythonw3.exe"]
    else:
        assert sorted(w[2]["name"] for w in written) == ["python3.exe", "pythonw3.exe"]
    # Ensure we still only have the two targets
    assert set(w[3].name for w in written) == {"p.exe", "pw.exe"}

