import pytest

from manage.tagutils import CompanyTag, TagRange, tag_or_range, install_matches_any


@pytest.mark.parametrize("tag_str", [
    "3.13", "3.13-32", "3.13-arm64",
    "cpython/3.13", "PythonCore\\3.13",
    "\\Tag",
])
def test_core_tag(tag_str):
    tag = CompanyTag(tag_str)

    assert tag.is_core

@pytest.mark.parametrize("tag_str", [
    "Company/Tag", "Company\\Tag", "Company/"
])
def test_company_tag(tag_str):
    tag = CompanyTag(tag_str)

    assert not tag.is_core


def test_tag_equality():
    assert CompanyTag("3.13") == CompanyTag("PythonCore\\3.13")
    assert CompanyTag("3.13") != CompanyTag("Company\\3.13")
    assert CompanyTag("3.13.0") == CompanyTag("3.13")
    assert CompanyTag("3.13.1") != CompanyTag("3.13")


def test_tag_match():
    assert not CompanyTag("3.13").match(CompanyTag("Company\\3.13"))
    assert CompanyTag("3.13").match(CompanyTag("3.13"))
    assert CompanyTag("3.13.0").match(CompanyTag("3.13"))
    assert CompanyTag("3.13.2").match(CompanyTag("3.13"))
    assert not CompanyTag("3.13").match(CompanyTag("3.13.0"))
    assert not CompanyTag("3.13").match(CompanyTag("3.13.2"))

    assert CompanyTag("PythonCore\\3.13").match(CompanyTag("", ""))
    assert CompanyTag("PythonCore\\4.56").match(CompanyTag("", ""))
    assert CompanyTag("PythonCore\\3.13").match(CompanyTag("", "3"))
    assert not CompanyTag("PythonCore\\4.56").match(CompanyTag("", "3"))

    assert CompanyTag("3.14T-extra").match(CompanyTag("3.14t"))
    assert not CompanyTag("3.14test").match(CompanyTag("3.14t"))
    assert not CompanyTag("3.14t").match(CompanyTag("3.14test"))
    assert CompanyTag("3.14-EMBED-extra").match(CompanyTag("3.14-embed"))
    assert not CompanyTag("3.14-embed").match(CompanyTag("3.14-emb"))
    assert CompanyTag("CompanyName\\3.14").match(CompanyTag("Company\\3.14"))


def test_tag_prerelease_match():
    assert CompanyTag("3.14rc1t").match(CompanyTag("3.14rc1t"))
    assert CompanyTag("3.14RC1T").match(CompanyTag("3.14rc1t"))
    assert not CompanyTag("3.14rc1t").match(CompanyTag("3.14rc2t"))
    assert not CompanyTag("3.14rc1t").match(CompanyTag("3.14t"))
    assert not CompanyTag("3.14rc1t").match(CompanyTag("3.14rc1"))
    assert not CompanyTag("3.14").match(CompanyTag("3.14rc1"))


def test_prefer_prerelease():
    assert not tag_or_range("3").prefers_prerelease
    assert not tag_or_range("3-64").prefers_prerelease
    assert not tag_or_range("3.13").prefers_prerelease
    assert not tag_or_range("3.14dev").prefers_prerelease
    assert not tag_or_range("3.14DEV-64").prefers_prerelease
    assert not tag_or_range("3.14rc1dev").prefers_prerelease
    assert not tag_or_range("3.14-devtools").prefers_prerelease
    assert tag_or_range("3-dev").prefers_prerelease
    assert tag_or_range("3.13-DEV").prefers_prerelease
    assert tag_or_range("3.13-dev-64").prefers_prerelease
    assert tag_or_range("3.14dev-dev").prefers_prerelease

    assert not tag_or_range(">3").prefers_prerelease
    assert not tag_or_range("<3-64").prefers_prerelease
    assert not tag_or_range("==3.13").prefers_prerelease
    assert not tag_or_range(">=3.14dev").prefers_prerelease
    assert not tag_or_range("!=3.13").prefers_prerelease
    assert not tag_or_range("!=3.13-dev").prefers_prerelease
    assert tag_or_range(">3-dev").prefers_prerelease
    assert tag_or_range("<3.13-DEV").prefers_prerelease
    assert tag_or_range("==3.13-dev-64").prefers_prerelease


def test_tag_platform_match():
    assert CompanyTag("3.10-64").match(CompanyTag("3.10"))
    assert CompanyTag("3.10-64").match(CompanyTag("3.10-64"))
    assert not CompanyTag("3.10").match(CompanyTag("3.10-64"))
    assert not CompanyTag("3.10-arm64").match(CompanyTag("3.10-64"))


def test_tag_platform_case():
    assert CompanyTag("3.10-ARM64") == CompanyTag("3.10-arm64")
    assert CompanyTag("3.10-ArM64").match(CompanyTag("3.10-arm64"))
    assert CompanyTag("3.10-arm64").match(CompanyTag("3.10-ARM64"))
    assert CompanyTag("3.10-ARM64").match(CompanyTag("3.10"))
    assert not CompanyTag("3.10").match(CompanyTag("3.10-ARM64"))
    assert not CompanyTag("3.10-ARM64").match(CompanyTag("3.10-64"))
    assert CompanyTag("3.10-32") < CompanyTag("3.10-ARM64")
    assert TagRange(">=3.10-ARM64").satisfied_by(CompanyTag("3.11-arm64"))
    assert TagRange(">=3.10-arm64").satisfied_by(CompanyTag("3.11-ArM64"))
    assert not TagRange(">=3.10-ARM64").satisfied_by(CompanyTag("3.11-64"))


def test_tag_order():
    assert CompanyTag("3.13.2") < CompanyTag("3.13")
    assert CompanyTag("3.13.1") < CompanyTag("3.13.1-32")
    assert CompanyTag("3.13.1") < CompanyTag("3.13.1-arm64")
    assert CompanyTag("3.13.1") < CompanyTag("a3.13.1")
    assert CompanyTag("a3.13.1") < CompanyTag("b3.13.1")
    assert CompanyTag("3.13.1a") < CompanyTag("3.13.1b")
    assert CompanyTag("3.13.1a") < CompanyTag("3.13.1b")


def test_tag_sort():
    import random
    tags = list(map(CompanyTag, [
        "3.11-64", "3.10.4", "3.10", "3.9", "3.9-32",
        "Company/Version10", "Company/Version9",
        "OtherCompany/3.9.2", "OtherCompany/3.9-32"
    ]))
    expected = list(tags)
    random.shuffle(tags)
    actual = sorted(tags)
    assert actual == expected, actual


def test_simple_tag_range():
    assert TagRange(">=3.10").satisfied_by(CompanyTag("3.10"))
    assert TagRange(">=3.10").satisfied_by(CompanyTag("3.10.1"))
    assert TagRange(">=3.10").satisfied_by(CompanyTag("3.11"))
    assert TagRange(">=3.10").satisfied_by(CompanyTag("4.0"))
    assert not TagRange(">=3.10").satisfied_by(CompanyTag("3.9"))
    assert not TagRange(">=3.10").satisfied_by(CompanyTag("2.0"))

    assert not TagRange(">3.10").satisfied_by(CompanyTag("3.9"))
    assert not TagRange(">3.10").satisfied_by(CompanyTag("3.10"))
    assert not TagRange(">3.10").satisfied_by(CompanyTag("3.10.0"))
    assert not TagRange(">3.10").satisfied_by(CompanyTag("3.10.1"))
    assert TagRange(">3.10").satisfied_by(CompanyTag("3.11"))

    assert TagRange("<=3.10").satisfied_by(CompanyTag("3.10"))
    assert TagRange("<=3.10").satisfied_by(CompanyTag("3.9"))
    assert TagRange("<=3.10").satisfied_by(CompanyTag("2.0"))
    assert not TagRange("<=3.10").satisfied_by(CompanyTag("3.11"))
    assert not TagRange("<=3.10").satisfied_by(CompanyTag("4.0"))

    assert not TagRange("<3.10").satisfied_by(CompanyTag("3.11"))
    assert not TagRange("<3.10").satisfied_by(CompanyTag("3.10"))
    assert not TagRange("<3.10").satisfied_by(CompanyTag("3.10.0"))
    assert not TagRange("<3.10").satisfied_by(CompanyTag("3.10.1"))
    assert TagRange("<3.10").satisfied_by(CompanyTag("3.9"))

    assert TagRange("=3.10").satisfied_by(CompanyTag("3.10"))
    assert TagRange("=3.10").satisfied_by(CompanyTag("3.10.1"))
    assert not TagRange("=3.10").satisfied_by(CompanyTag("3.9"))
    assert not TagRange("=3.10").satisfied_by(CompanyTag("3.11"))
    assert TagRange("~=3.10").satisfied_by(CompanyTag("3.10"))
    assert TagRange("~=3.10").satisfied_by(CompanyTag("3.10.1"))
    assert not TagRange("~=3.10").satisfied_by(CompanyTag("3.9"))
    assert not TagRange("~=3.10").satisfied_by(CompanyTag("3.11"))

    assert TagRange(">3.14.1").satisfied_by(CompanyTag("3.15"))
    assert TagRange("<3.14.1").satisfied_by(CompanyTag("3.13"))
    assert not TagRange(">3.14.1").satisfied_by(CompanyTag("3.14"))
    assert TagRange(">=3.14.0").satisfied_by(CompanyTag("3.14"))
    assert TagRange("<=3.14.0").satisfied_by(CompanyTag("3.14"))
    assert not TagRange(">3.14.0").satisfied_by(CompanyTag("3.14"))
    assert not TagRange("<3.14.0").satisfied_by(CompanyTag("3.14"))
    assert not TagRange("!=3.14.0").satisfied_by(CompanyTag("3.14"))


@pytest.mark.parametrize("spec, tag, expected", [
    (">=3.13", "3.13.4", True),
    (">=3.13", "3.14", True),
    (">3.13", "3.14", True),
    (">3.13", "3.13.4", False),
    (">=3.13t", "3.14t", True),
    (">=3.13", "3.14t", False),
    (">=3.13", "3.14-abc", True),
    (">=3.13", "3.14abc", False),
    (">3.13-abc-123", "3.14", True),
    (">3.13-abc-123", "3.13-abc-124", True),
    (">3.13-abc-123", "3.13-def-123", False),
    (">3.13-abc-123", "3.13def-123", False),
    (">3.13-abc-123", "3.13-abc-123", False),
    (">3.13-abc-123", "3.13-abc", False),
])
def test_tag_range_examples(spec, tag, expected):
    assert TagRange(spec).satisfied_by(CompanyTag(tag)) == expected


def test_tag_range_prereleases():
    assert TagRange(">3.14a9").satisfied_by(CompanyTag("3.14a10"))
    assert TagRange("<3.14a10").satisfied_by(CompanyTag("3.14a9"))
    assert TagRange(">3.14a10").satisfied_by(CompanyTag("3.14b1"))
    assert TagRange(">3.14b1").satisfied_by(CompanyTag("3.14rc1"))
    assert TagRange(">3.14rc1").satisfied_by(CompanyTag("3.14"))
    assert TagRange("<3.14").satisfied_by(CompanyTag("3.14rc1"))
    assert not TagRange(">=3.14").satisfied_by(CompanyTag("3.14rc1"))
    assert not TagRange("=3.14a1").satisfied_by(CompanyTag("3.14a2"))
    assert TagRange(">3.14.0a1").satisfied_by(CompanyTag("3.14a2"))
    assert TagRange("<3.14.0rc1").satisfied_by(CompanyTag("3.14b1"))
    assert TagRange(">=3.14.0rc1").satisfied_by(CompanyTag("3.14rc1"))


def test_tag_range_variants():
    assert TagRange(">=3.13t").satisfied_by(CompanyTag("3.14t"))
    assert TagRange("<3.14t").satisfied_by(CompanyTag("3.13t"))
    assert not TagRange(">3.13d").satisfied_by(CompanyTag("3.13"))
    assert not TagRange(">1.1.1w").satisfied_by(CompanyTag("1.1.1"))
    assert not TagRange(">2024b").satisfied_by(CompanyTag("2024"))
    assert TagRange(">2024b1").satisfied_by(CompanyTag("2024"))
    assert not TagRange("=3.13d").satisfied_by(CompanyTag("3.13debug"))

    assert not TagRange(">3.13t").satisfied_by(CompanyTag("3.13-embed"))
    assert not TagRange(">3.13t-embed").satisfied_by(CompanyTag("3.13-embed"))
    assert TagRange("<3.14").satisfied_by(CompanyTag("3.13-embed"))


@pytest.mark.parametrize("op", ["<", "<=", ">", ">="])
def test_tag_range_different_variants(op):
    assert not TagRange(f"{op}3.13t").satisfied_by(CompanyTag("3.13"))
    assert not TagRange(f"{op}3.13").satisfied_by(CompanyTag("3.14t"))
    assert not TagRange(f"{op}3.13").satisfied_by(CompanyTag("3.12t"))


def test_tag_range_prerelease_variants():
    assert TagRange(">3.14a9t").satisfied_by(CompanyTag("3.14a10t"))
    assert TagRange(">3.14a10t").satisfied_by(CompanyTag("3.14rc1t"))
    assert TagRange(">3.14rc1t").satisfied_by(CompanyTag("3.14t"))
    assert TagRange("<3.14t").satisfied_by(CompanyTag("3.14rc1t"))
    assert not TagRange(">3.14rc1t").satisfied_by(CompanyTag("3.14"))
    assert not TagRange(">=3.13a1t").satisfied_by(CompanyTag("3.14a1d"))


def test_tag_range_exclude():
    assert TagRange("!=3.10").satisfied_by(CompanyTag("3.11"))
    assert TagRange("!=3.10").satisfied_by(CompanyTag("3.9"))
    assert not TagRange("!=3.10").satisfied_by(CompanyTag("3.10"))
    assert not TagRange("!=3.10").satisfied_by(CompanyTag("3.10.0"))
    assert not TagRange("!=3.10").satisfied_by(CompanyTag("3.10.1"))


def test_tag_range_platforms():
    assert TagRange(">=3.10-32").satisfied_by(CompanyTag("3.10-32"))
    assert TagRange(">=3.10-32").satisfied_by(CompanyTag("3.10.1-32"))
    assert TagRange(">=3.10").satisfied_by(CompanyTag("3.10-32"))
    assert not TagRange(">=3.10-32").satisfied_by(CompanyTag("3.10-64"))
    assert not TagRange(">=3.10-32").satisfied_by(CompanyTag("3.10.1"))


def test_tag_range_suffixes():
    assert TagRange(">=3.10").satisfied_by(CompanyTag("3.10-embed"))
    assert not TagRange(">=3.10-embed").satisfied_by(CompanyTag("3.10"))
    assert TagRange(">=3.10-embed").satisfied_by(CompanyTag("3.10-embed"))
    assert not TagRange("<3.13-abc-1").satisfied_by(CompanyTag("4-abc-0"))
    assert TagRange("<3.13-abc-1").satisfied_by(CompanyTag("3-abc-2"))
    assert TagRange(">3.13-abc-123").satisfied_by(CompanyTag("4-abc-0"))
    assert TagRange(">=3.0-abc-1").satisfied_by(CompanyTag("3-abc-1"))
    assert TagRange(">3.13-abc-123").satisfied_by(CompanyTag("3.14-def-122"))
    assert TagRange("<3.13-abc-123").satisfied_by(CompanyTag("3.12-def"))
    assert not TagRange(">3.13-abc-123").satisfied_by(CompanyTag("3.14def-122"))
    assert not TagRange("<3.13-abc-123").satisfied_by(CompanyTag("3.12def"))
    assert not TagRange("<3.13-abc-123").satisfied_by(CompanyTag("3.14"))
    assert not TagRange(">=3.13-abc-123").satisfied_by(CompanyTag("3.13-abc"))
    assert not TagRange("<=3.13-abc-123").satisfied_by(CompanyTag("3.13-abc"))


@pytest.mark.parametrize("for_run", [False, True])
def test_install_matches_any_ranges(for_run):
    install = {
        "company": "PythonCore",
        "tag": "3.14t",
        "install-for": ["3.14"],
        "run-for": [{"tag": "3.14w"}],
    }
    assert install_matches_any(install, [TagRange(">=3.14")], for_run=for_run) == (not for_run)
    assert install_matches_any(install, [TagRange(">=3.14w")], for_run=for_run) == for_run
    assert not install_matches_any(install, [TagRange(">=3.14t")], for_run=for_run)

    install["install-for"] = ["3.13", "3.15"]
    install["run-for"] = [{"tag": "3.13"}, {"tag": "3.15"}]
    assert not install_matches_any(install, [TagRange(">=3.14,<3.15")], for_run=for_run)

    install["install-for"] = []
    install["run-for"] = []
    assert install_matches_any(install, [TagRange(">=3.14t")], for_run=for_run)
    del install["install-for"], install["run-for"]
    assert install_matches_any(install, [TagRange(">=3.14t")], for_run=for_run)


def test_tag_range_company():
    assert TagRange(r">=Company\3.10").satisfied_by(CompanyTag("Company", "3.10"))
    assert TagRange(r">=Company\3.10").satisfied_by(CompanyTag("Company", "3.11"))
    assert not TagRange(r">=Company\3.10").satisfied_by(CompanyTag("Company", "3.9"))
    assert not TagRange(r">=Company\3.10").satisfied_by(CompanyTag("OtherCompany", "3.10"))

    assert TagRange("=Company\\").satisfied_by(CompanyTag("Company", "3.11"))


def test_tag_concatenate():
    assert CompanyTag("3.13") + "-64" == CompanyTag("3.13-64")
    assert CompanyTag("3.13-64") + "-64" == CompanyTag("3.13-64-64")
    assert CompanyTag("3.13-arm64") + "-64" == CompanyTag("3.13-arm64-64")
