import pytest
import winreg

from manage import pep514utils

REG_TEST_ROOT = r"Software\Python\PyManagerTesting"

@pytest.fixture(scope='function')
def registry():
    try:
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, REG_TEST_ROOT) as key:
            yield key
    finally:
        pep514utils._reg_rmtree(winreg.HKEY_CURRENT_USER, REG_TEST_ROOT)


def init_reg(registry, **keys):
    for k, v in keys.items():
        if isinstance(v, dict):
            with winreg.CreateKey(registry, k) as subkey:
                init_reg(subkey, **v)
        elif isinstance(v, str):
            winreg.SetValueEx(registry, k, None, winreg.REG_SZ, v)
        elif isinstance(v, (bytes, bytearray)):
            winreg.SetValueEx(registry, k, None, winreg.REG_BINARY, v)
        elif isinstance(v, int):
            if v.bit_count() < 32:
                winreg.SetValueEx(registry, k, None, winreg.REG_DWORD, v)
            else:
                winreg.SetValueEx(registry, k, None, winreg.REG_QWORD, v)
        else:
            raise TypeError("unsupported type in registry")


def test_is_tag_managed(registry, tmp_path):
    init_reg(registry, Company={
        "1.0": {"InstallPath": {"": str(tmp_path)}},
        "2.0": {"InstallPath": {"": str(tmp_path)}, "ManagedByPyManager": 0},
        "2.1": {"InstallPath": {"": str(tmp_path)}, "ManagedByPyManager": 1},
        "3.0": {"InstallPath": {"": str(tmp_path / "missing")}},
        "3.0.0": {"": "Just in the way here"},
        "3.0.1": {"": "Also in the way here"},
    })

    assert not pep514utils._is_tag_managed(registry, r"Company\1.0")
    assert not pep514utils._is_tag_managed(registry, r"Company\2.0")
    assert pep514utils._is_tag_managed(registry, r"Company\2.1")

    assert not pep514utils._is_tag_managed(registry, r"Company\3.0")
    with pytest.raises(FileNotFoundError):
        winreg.OpenKey(registry, r"Company\3.0.2")
    assert pep514utils._is_tag_managed(registry, r"Company\3.0", creating=True)
    with winreg.OpenKey(registry, r"Company\3.0.2"):
        pass
