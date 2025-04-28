import pytest

from manage.tagutils import CompanyTag, TagRange


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
    assert CompanyTag("3.13.0") != CompanyTag("3.13")


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


def test_tag_platform_match():
    assert CompanyTag("3.10-64").match(CompanyTag("3.10"))
    assert CompanyTag("3.10-64").match(CompanyTag("3.10-64"))
    assert not CompanyTag("3.10").match(CompanyTag("3.10-64"))
    assert not CompanyTag("3.10-arm64").match(CompanyTag("3.10-64"))


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


def test_tag_range_company():
    assert TagRange(r">=Company\3.10").satisfied_by(CompanyTag("Company", "3.10"))
    assert TagRange(r">=Company\3.10").satisfied_by(CompanyTag("Company", "3.11"))
    assert not TagRange(r">=Company\3.10").satisfied_by(CompanyTag("Company", "3.9"))
    assert not TagRange(r">=Company\3.10").satisfied_by(CompanyTag("OtherCompany", "3.10"))

    assert TagRange("=Company\\").satisfied_by(CompanyTag("Company", "3.11"))
