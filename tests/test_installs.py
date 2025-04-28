import pytest

from pathlib import PurePath

from manage import installs


def make_install(tag, **kwargs):
    run_for = [
        {"tag": tag, "target": kwargs.get("target", "python.exe")},
        {"tag": tag, "target": kwargs.get("targetw", "pythonw.exe"), "windowed": 1},
    ]

    return {
        "company": kwargs.get("company", "PythonCore"),
        "id": "{}-{}".format(kwargs.get("company", "PythonCore"), tag),
        "sort-version": kwargs.get("sort_version", tag),
        "tag": tag,
        "install-for": [tag],
        "run-for": run_for,
        "prefix": PurePath(kwargs.get("prefix", rf"C:\{tag}")),
        "executable": kwargs.get("executable", "python.exe"),
    }


def fake_get_installs(install_dir):
    yield make_install("1.0")
    yield make_install("1.0-32", sort_version="1.0")
    yield make_install("1.0-64", sort_version="1.0")
    yield make_install("2.0-64", sort_version="2.0")
    yield make_install("2.0-arm64", sort_version="2.0")
    yield make_install("3.0a1-32", sort_version="3.0a1")
    yield make_install("3.0a1-64", sort_version="3.0a1")
    yield make_install("1.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("1.1-64", sort_version="1.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("1.1-arm64", sort_version="1.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("2.1", sort_version="2.1", company="Company", target="company.exe", targetw="companyw.exe")
    yield make_install("2.1-64", sort_version="2.1", company="Company", target="company.exe", targetw="companyw.exe")


def fake_get_installs2(install_dir):
    yield make_install("1.0-32", sort_version="1.0")
    yield make_install("3.0a1-32", sort_version="3.0a1")
    yield make_install("3.0a1-64", sort_version="3.0a1")
    yield make_install("3.0a1-arm64", sort_version="3.0a1")


def fake_get_unmanaged_installs():
    return []


def fake_get_venv_install(virtualenv):
    raise LookupError


@pytest.fixture
def patched_installs(monkeypatch):
    monkeypatch.setattr(installs, "_get_installs", fake_get_installs)
    monkeypatch.setattr(installs, "_get_unmanaged_installs", fake_get_unmanaged_installs)
    monkeypatch.setattr(installs, "_get_venv_install", fake_get_venv_install)


@pytest.fixture
def patched_installs2(monkeypatch):
    monkeypatch.setattr(installs, "_get_installs", fake_get_installs2)
    monkeypatch.setattr(installs, "_get_unmanaged_installs", fake_get_unmanaged_installs)
    monkeypatch.setattr(installs, "_get_venv_install", fake_get_venv_install)


def test_get_installs_in_order(patched_installs):
    ii = installs.get_installs("<none>")
    assert [i["id"] for i in ii] == [
        "PythonCore-2.0-64",
        "PythonCore-2.0-arm64",
        "PythonCore-1.0",
        "PythonCore-1.0-64",
        "PythonCore-1.0-32",
        # Note that the order is subtly different for non-PythonCore
        "Company-2.1",
        "Company-2.1-64",
        "Company-1.1",
        "Company-1.1-64",
        "Company-1.1-arm64",
        # Prereleases come last
        "PythonCore-3.0a1-64",
        "PythonCore-3.0a1-32",
    ]


def test_get_default_install(patched_installs):
    assert installs.get_install_to_run("<none>", "1.0", "")["id"] == "PythonCore-1.0"
    assert installs.get_install_to_run("<none>", "2.0-64", "")["id"] == "PythonCore-2.0-64"

    assert installs.get_install_to_run("<none>", "1.1", "")["id"] == "Company-1.1"
    assert installs.get_install_to_run("<none>", "2.1-64", "")["id"] == "Company-2.1-64"


def test_get_default_with_default_platform(patched_installs):
    i = installs.get_install_to_run("<none>", "1", "", default_platform="-64")
    assert i["id"] == "PythonCore-1.0-64"
    i = installs.get_install_to_run("<none>", "1", "", default_platform="-32")
    assert i["id"] == "PythonCore-1.0-32"


def test_get_install_to_run(patched_installs):
    i = installs.get_install_to_run("<none>", None, "1.0")
    assert i["id"] == "PythonCore-1.0"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, "2.0")
    assert i["id"] == "PythonCore-2.0-64"
    assert i["executable"].match("python.exe")


def test_get_install_to_run_with_platform(patched_installs):
    i = installs.get_install_to_run("<none>", None, "1.0-32")
    assert i["id"] == "PythonCore-1.0-32"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, "2.0-arm64")
    assert i["id"] == "PythonCore-2.0-arm64"
    assert i["executable"].match("python.exe")


def test_get_install_to_run_with_platform(patched_installs):
    i = installs.get_install_to_run("<none>", None, "1.0-32", windowed=True)
    assert i["id"] == "PythonCore-1.0-32"
    assert i["executable"].match("pythonw.exe")
    i = installs.get_install_to_run("<none>", None, "2.0-arm64", windowed=True)
    assert i["id"] == "PythonCore-2.0-arm64"
    assert i["executable"].match("pythonw.exe")


def test_get_install_to_run_with_default_platform(patched_installs):
    i = installs.get_install_to_run("<none>", None, "1.0", default_platform="-32")
    assert i["id"] == "PythonCore-1.0-32"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, "1.0", default_platform="-64")
    assert i["id"] == "PythonCore-1.0-64"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, "2.0", default_platform="-arm64")
    assert i["id"] == "PythonCore-2.0-arm64"
    assert i["executable"].match("python.exe")

    i = installs.get_install_to_run("<none>", None, "1.0-64", default_platform="-32")
    assert i["id"] == "PythonCore-1.0-64"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, "2.0-64", default_platform="-arm64")
    assert i["id"] == "PythonCore-2.0-64"
    assert i["executable"].match("python.exe")


def test_get_install_to_run_with_default_platform_prerelease(patched_installs2):
    # Specifically testing issue #25, where a native prerelease is preferred
    # over a non-native stable release. We should prefer the stable release
    # (e.g. for cases where an ARM64 user is relying on a stable x64 build, but
    # also wanting to test a prerelease ARM64 build.)
    i = installs.get_install_to_run("<none>", None, None, default_platform="-32")
    assert i["id"] == "PythonCore-1.0-32"
    i = installs.get_install_to_run("<none>", None, None, default_platform="-64")
    assert i["id"] == "PythonCore-1.0-32"
    i = installs.get_install_to_run("<none>", None, None, default_platform="-arm64")
    assert i["id"] == "PythonCore-1.0-32"


def test_get_install_to_run_with_range(patched_installs):
    i = installs.get_install_to_run("<none>", None, "<=1.0")
    assert i["id"] == "PythonCore-1.0"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, ">1.0")
    assert i["id"] == "PythonCore-2.0-64"
    assert i["executable"].match("python.exe")
