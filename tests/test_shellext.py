import pytest
import sys
import winreg

import _shellext_test as SE

def test_RegReadStr():
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Volatile Environment") as key:
        assert SE.shellext_RegReadStr(key.handle, "USERPROFILE")
        with pytest.raises(FileNotFoundError):
            assert SE.shellext_RegReadStr(key.handle, "a made up name that hopefully doesn't exist")
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, "Environment") as key:
        # PATH should be REG_EXPAND_SZ, which is not supported
        with pytest.raises(OSError) as ex:
            SE.shellext_RegReadStr(key.handle, "PATH")
        assert ex.value.winerror == 13


class IdleReg:
    def __init__(self, registry, tmp_path):
        self.registry = registry
        self.hkey = registry.key.handle
        self.tmp_path = tmp_path
        python_exe = tmp_path / "python.exe"
        idle_pyw = tmp_path / "Lib/idlelib/idle.pyw"
        self.python_exe = str(python_exe)
        self.idle_pyw = str(idle_pyw)

        python_exe.parent.mkdir(parents=True, exist_ok=True)
        idle_pyw.parent.mkdir(parents=True, exist_ok=True)
        python_exe.write_bytes(b"")
        idle_pyw.write_bytes(b"")

        registry.setup(
            PythonCore={
                "1.0": {
                    "DisplayName": "PythonCore-1.0",
                    "InstallPath": {
                        "": str(tmp_path),
                    }
                },
            },
            # Even if all the pieces are there, we won't pick up non-PythonCore
            # unless they specify IdlePath
            NotPythonCore={
                "1.0": {
                    "DisplayName": "NotPythonCore-1.0",
                    "InstallPath": {
                        "": str(tmp_path),
                    }
                },
                "2.0": {
                    "DisplayName": "NotPythonCore-2.0",
                    "InstallPath": {
                        "": str(tmp_path),
                        "WindowedExecutablePath": str(python_exe),
                        "IdlePath": str(idle_pyw),
                    }
                },
            },
        )

        self.pythoncore_1_0 = ("PythonCore-1.0", self.python_exe, self.idle_pyw)
        self.pythoncore = [self.pythoncore_1_0]
        # NotPythonCore-1.0 should never get returned
        self.notpythoncore_1_0 = ("NotPythonCore-1.0", self.python_exe, self.idle_pyw)
        self.notpythoncore_2_0 = ("NotPythonCore-2.0", self.python_exe, self.idle_pyw)
        self.notpythoncore = [self.notpythoncore_2_0]
        self.all = [*self.notpythoncore, *self.pythoncore]


@pytest.fixture(scope='function')
def idle_reg(registry, tmp_path):
    return IdleReg(registry, tmp_path)


def test_ReadIdleInstalls(idle_reg):
    inst = SE.shellext_ReadIdleInstalls(idle_reg.hkey, "PythonCore", 0)
    assert inst == idle_reg.pythoncore
    inst = SE.shellext_ReadIdleInstalls(idle_reg.hkey, "NotPythonCore", 0)
    assert inst == idle_reg.notpythoncore


def test_ReadAllIdleInstalls(idle_reg):
    inst = SE.shellext_ReadAllIdleInstalls(idle_reg.hkey, 0)
    assert inst == [
        *idle_reg.notpythoncore,
        *idle_reg.pythoncore,
    ]


def test_PassthroughTitle():
    assert "Test" == SE.shellext_PassthroughTitle("Test")
    assert "Test \u0ABC" == SE.shellext_PassthroughTitle("Test \u0ABC")


def test_IdleCommand(idle_reg):
    data = SE.shellext_IdleCommand(idle_reg.hkey)
    assert data == [
        "Edit in &IDLE",
        f"{sys._base_executable},-4",
        *(i[0] for i in reversed(idle_reg.all)),
    ]
