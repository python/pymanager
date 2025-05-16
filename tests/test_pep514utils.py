import pytest
import winreg

from manage import pep514utils
from manage import tagutils

def test_is_tag_managed(registry, tmp_path):
    registry.setup(Company={
        "1.0": {"InstallPath": {"": str(tmp_path)}},
        "2.0": {"InstallPath": {"": str(tmp_path)}, "ManagedByPyManager": 0},
        "2.1": {"InstallPath": {"": str(tmp_path)}, "ManagedByPyManager": 1},
        "3.0": {"InstallPath": {"": str(tmp_path / "missing")}},
        "3.0.0": {"": "Just in the way here"},
        "3.0.1": {"": "Also in the way here"},
    })

    assert not pep514utils._is_tag_managed(registry.key, r"Company\1.0")
    assert not pep514utils._is_tag_managed(registry.key, r"Company\2.0")
    assert pep514utils._is_tag_managed(registry.key, r"Company\2.1")

    assert not pep514utils._is_tag_managed(registry.key, r"Company\3.0")
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(registry.key, r"Company\3.0.2")
    assert pep514utils._is_tag_managed(registry.key, r"Company\3.0", creating=True)
    with winreg.OpenKey(registry.key, r"Company\3.0.2"):
        pass


def test_is_tag_managed_warning_suppressed(registry, tmp_path, assert_log):
    registry.setup(Company={
        "3.0.0": {"": "Just in the way here"},
        "3.0.1": {"": "Also in the way here"},
    })
    pep514utils.update_registry(
        rf"HKEY_CURRENT_USER\{registry.root}",
        dict(company="Company", tag="3.0.0"),
        dict(kind="pep514", Key="Company\\3.0.0", InstallPath=dict(_="dir")),
        warn_for=[tagutils.tag_or_range(r"Company\3.0.1")],
    )
    assert_log(
        "Registry key %s appears invalid.+",
        assert_log.not_logged("An existing runtime is registered at %s"),
    )


def test_is_tag_managed_warning(registry, tmp_path, assert_log):
    registry.setup(Company={
        "3.0.0": {"": "Just in the way here"},
        "3.0.1": {"": "Also in the way here"},
    })
    pep514utils.update_registry(
        rf"HKEY_CURRENT_USER\{registry.root}",
        dict(company="Company", tag="3.0.0"),
        dict(kind="pep514", Key="Company\\3.0.0", InstallPath=dict(_="dir")),
        warn_for=[tagutils.tag_or_range(r"Company\3.0.0")],
    )
    assert_log(
        "Registry key %s appears invalid.+",
        assert_log.skip_until("An existing registry key for %s"),
    )
