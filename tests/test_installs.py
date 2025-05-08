import pytest

from pathlib import PurePath

from manage import installs


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


def test_get_default_install_prerelease(patched_installs2):
    inst = list(installs._get_installs("<none>"))
    m = installs.get_matching_install_tags(inst, "1.0", None, "-32", single_tag=True)
    assert m and m[0]
    assert m[0][0]["id"] == "PythonCore-1.0-32"

    m = installs.get_matching_install_tags(inst, "3.0", None, "-32", single_tag=True)
    assert m and m[0]
    assert m[0][0]["id"] == "PythonCore-3.0a1-32"


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


def test_get_install_to_run_with_platform_windowed(patched_installs):
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


def test_get_install_to_run_with_platform_prerelease(patched_installs2):
    i = installs.get_install_to_run("<none>", None, "3", default_platform="-32")
    assert i["id"] == "PythonCore-3.0a1-32"
    i = installs.get_install_to_run("<none>", None, "3-32", default_platform="-64")
    assert i["id"] == "PythonCore-3.0a1-32"
    i = installs.get_install_to_run("<none>", None, "3-32", default_platform="-arm64")
    assert i["id"] == "PythonCore-3.0a1-32"


def test_get_install_to_run_with_range(patched_installs):
    i = installs.get_install_to_run("<none>", None, "<=1.0")
    assert i["id"] == "PythonCore-1.0"
    assert i["executable"].match("python.exe")
    i = installs.get_install_to_run("<none>", None, ">1.0")
    assert i["id"] == "PythonCore-2.0-64"
    assert i["executable"].match("python.exe")
