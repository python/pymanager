import pytest
import winreg

from manage import pep514utils

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
