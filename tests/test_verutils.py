import pytest

from manage.verutils import Version


@pytest.mark.parametrize("ver_str", [
    "3", "3.1", "3.10", "3.1.2", "3.1.2.3",
    "3a1", "3.1a1", "3.1.2a2", "3.1.2-a2", "3.1.a.4",
    "3.1b1", "3.1c1", "3.1rc1",
    "3.*", "3*",
    "3.1dev0", "3.2-dev",
])
def test_version(ver_str):
    ver = Version(ver_str)
    assert ver
    assert str(ver) == ver_str
    assert ver == ver_str


def test_long_version(assert_log):
    v = "3.1.2.3.4.5.6.7.8.9"
    v2 = "3.1.2.3.4.5.6.7"
    Version(v)
    assert_log(
        (".*is too long.*", (v, v2)),
    )


def test_sort_versions():
    import random
    cases = ["3", "3.0", "3.1", "3.1.0", "3.2-a0", "3.2.0.1-a0", "3.2.0.1-b1"]
    expect = list(cases)
    random.shuffle(cases)
    actual = sorted(cases, key=Version)
    assert actual == expect


def test_version_prerelease():
    assert Version("3.14a0").is_prerelease
    assert Version("3.14-dev").is_prerelease
    assert not Version("3.14").is_prerelease


def test_version_prerelease_order():
    assert Version("3.14.0-a1") < "3.14.0-a2"
    assert Version("3.14.0-a2") > "3.14.0-a1"
    assert Version("3.14.0-a1") == "3.14.0-a1"
    assert Version("3.14.0-b1") > "3.14.0-a1"


@pytest.mark.parametrize("ver_str", ["3.14.0", "3.14.0-a1", "3.14.20-dev", "3.14.0.0.0.0"])
def test_version_wildcard(ver_str):
    wild = Version("3.14.*")
    ver = Version(ver_str)
    assert wild == ver
    assert ver == wild


@pytest.mark.parametrize("ver_str", ["3.14.0", "3.14.0-a1", "3.14.0.0.0-dev"])
def test_version_dev(ver_str):
    wild = Version("3.14-dev")
    ver = Version(ver_str)
    assert wild == ver


def test_version_startswith():
    assert Version("3.13.0").startswith(Version("3.13"))
    assert Version("3.13.0").startswith(Version("3.13.0"))
    assert not Version("3.13").startswith(Version("3.13.0"))
