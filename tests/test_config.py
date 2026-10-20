import os
import pytest

from pathlib import Path, PurePath

from manage.config import (
    _EnvironWithFallback,
    _expand_vars,
    config_append,
    config_bool,
    config_dict_merge,
    config_split,
    config_split_append,
    resolve_config,
)


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, False),
        ("", False),
        ("true", True),
        (0, False),
        ("TRUE", True),
        ("True", True),
        ("yes", True),
        ("1", True),
        ("false", False),
        ("no", False),
        ("0", False),
        ("yellow", True),
        ("%PYTHON_MANAGER_CONFIRM%", False),
        (True, True),
        (42, True),
        (["x"], True),
    ],
    ids=[
        "none",
        "str_empty",
        "str_true_lower",
        "int_zero",
        "str_true_upper",
        "str_true_title",
        "str_yes",
        "str_one",
        "str_false",
        "str_no",
        "str_zero",
        "str_yellow",
        "str_environment_variable",
        "bool_true",
        "int_positive",
        "list_nonempty",
    ],
)
def test_config_bool(value, expected):
    assert config_bool(value) is expected


def test_config_bool_any_t_prefixed_string_is_true():
    assert config_bool("tomato") is True


@pytest.mark.parametrize(
    ("value", "variables", "expected"),
    [
        ("%FOO%", {"FOO": "bar"}, "bar"),
        (
            "%LocalAppData%\\Python",
            {"LocalAppData": "C:\\Temp"},
            "C:\\Temp\\Python",
        ),
        ("./bundled/fallback-index.json", {}, "./bundled/fallback-index.json"),
        ("%A%%B%", {"A": "x", "B": "y"}, "xy"),
        (
            "%LocalAppData%\\Python\\_cache",
            {"LocalAppData": "C:\\Temp"},
            "C:\\Temp\\Python\\_cache",
        ),
        ("%FOO%/bar", {"FOO": "x"}, "x/bar"),
    ],
    ids=[
        "var_only",
        "var_with_separator",
        "no_vars",
        "adjacent_vars",
        "nested_path",
        "forward_slash",
    ],
)
def test_expand_vars(value, variables, expected):
    assert _expand_vars(value, variables) == expected


def test_expand_vars_fails_on_missing_variable():
    with pytest.raises(LookupError):
        _expand_vars("%MISSING%\\Python", {})


def test_expand_vars_fails_on_empty_variable():
    with pytest.raises(LookupError):
        _expand_vars("%EMPTY%\\Python", {"EMPTY": ""})


def test_environ_with_fallback():
    env = _EnvironWithFallback({"AllUsersProfile": "test", "APPDATA": ""})
    # Should be the value we provided, despite case
    assert env.get("allusersprofile") == "test"
    # Should be empty, since it was provided as empty
    assert env.get("AppData", "default") == ""
    # Should be set, even though it wasn't provided
    assert env.get("WinDir", "default") not in (None, "", "default")
    # Should be empty, since it's neither set nor has a fallback
    assert env.get("PYTHON_MANAGER_DEFAULT", "default") == "default"


@pytest.mark.parametrize(
    ("existing", "value", "expected"),
    [
        (None, "a", ["a"]),
        ("a", "b", ["a", "b"]),
        (["a"], "b", ["a", "b"]),
    ],
    ids=[
        "none",
        "scalar",
        "list",
    ],
)
def test_config_append(existing, value, expected):
    assert config_append(existing, value) == expected


def test_config_append_does_not_mutate_existing_list():
    existing = ["a"]

    actual = config_append(existing, "b")

    assert actual == ["a", "b"]
    assert existing == ["a"]
    assert actual is not existing


@pytest.mark.parametrize(
    ("existing", "new", "expected"),
    [
        ({"a": 1}, {"b": 2}, {"a": 1, "b": 2}),
        ({"a": 1}, {"a": 2}, {"a": 2}),
    ],
    ids=[
        "distinct_keys",
        "new_value_overwrites",
    ],
)
def test_config_dict_merge(existing, new, expected):
    assert config_dict_merge(existing, new) == expected


def test_config_dict_merge_does_not_mutate_inputs():
    existing = {"a": 1}
    new = {"b": 2}

    actual = config_dict_merge(existing, new)

    assert actual == {"a": 1, "b": 2}
    assert existing == {"a": 1}
    assert new == {"b": 2}
    assert actual is not existing
    assert actual is not new


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("", [""]),
        ("a,b", ["a", "b"]),
        ("a,,b", ["a", "", "b"]),
        ("C:\\tools", ["C", "\\tools"]),
        ("a;b:c|d+e", ["a", "b", "c", "d", "e"]),
    ],
    ids=[
        "empty",
        "comma",
        "consecutive_delimiters",
        "windows_path",
        "all_delimiters",
    ],
)
def test_config_split(value, expected):
    assert config_split(value) == expected


@pytest.mark.parametrize(
    ("existing", "value", "expected"),
    [
        (None, "a,b", [["a", "b"]]),
        ("existing", "a,b", ["existing", ["a", "b"]]),
        (["existing"], "a,b", ["existing", ["a", "b"]]),
    ],
    ids=[
        "none",
        "scalar",
        "list",
    ],
)
def test_config_split_append(existing, value, expected):
    assert config_split_append(existing, value) == expected


def test_config_split_append_does_not_mutate_existing_list():
    existing = ["first"]

    actual = config_split_append(existing, "second,third")

    assert actual == ["first", ["second", "third"]]
    assert existing == ["first"]
    assert actual is not existing


@pytest.mark.parametrize(
    ("cfg", "schema", "expect", "env"),
    [
        ({}, {"a": (int, None), "b": (int, None)}, {}, None),
        ({"a": "1"}, {"a": (int, None)}, {"a": 1}, None),
        ({"a": 1}, {"a": (str, None)}, {"a": "1"}, None),
        ({"a": "abc"}, {"a": (str, None, "path")}, {"a": PurePath("X:/test/abc")}, None),
        ({"a": "%X%"}, {"a": (str, None, "path")}, {"a": PurePath("X:/test/%X%")}, {"X": "abc"}),
        ({"a": "%X%"}, {"a": (str, None, "path", "env")}, {"a": PurePath("X:/env/abc")}, {"X": "X:/env/abc"}),
        ({"a": "%X%"}, {"a": (str, None, "path")}, {"a": PurePath("X:/test/%X%")}, None),
    ],
    ids=[
        "empty",
        "to_int",
        "to_str",
        "to_path",
        "to_path_without_env",
        "to_path_with_env",
        "to_path_not_in_env",
    ],
)
def test_config_resolve(cfg, schema, expect, env, monkeypatch):
    resolve_config(cfg, "<test.cfg>", PurePath("X:/test/"), schema=schema, environ=env)
    assert cfg == expect


def test_config_resolve_env_fallback(monkeypatch, assert_log):
    cfg = {"a": "%AppData%/Python"}
    schema = {"a": (str, None, "path", "env")}
    expect = {"a": Path(os.environ["AppData"]) / "Python"}
    monkeypatch.delitem(os.environ, "AppData")
    resolve_config(cfg, "<test.cfg>", Path(), schema=schema)
    assert cfg == expect
    assert_log(("Environment variable.*not found", ["AppData"]))
