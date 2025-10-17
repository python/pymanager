import winreg
from unittest import mock

import pytest

from manage import arputils
from manage.pathutils import Path


def test_size_empty_directory(tmp_path):
    result = arputils._size(tmp_path)
    assert result == 0


def test_size_with_files(tmp_path):
    (tmp_path / "file1.txt").write_bytes(b"x" * 1024)
    (tmp_path / "file2.txt").write_bytes(b"y" * 2048)
    
    result = arputils._size(tmp_path)
    assert result == 3


def test_size_ignores_oserror(tmp_path):
    (tmp_path / "file.txt").write_bytes(b"test")
    
    with mock.patch("manage.arputils.rglob") as mock_rglob:
        mock_file = mock.Mock()
        mock_file.lstat.side_effect = OSError("Access denied")
        mock_rglob.return_value = [mock_file]
        
        result = arputils._size(tmp_path)
        assert result == 0


def test_set_int_value():
    mock_key = mock.Mock()
    
    with mock.patch("winreg.SetValueEx") as mock_set:
        arputils._set_value(mock_key, "TestInt", 42)
        mock_set.assert_called_once_with(
            mock_key, "TestInt", None, winreg.REG_DWORD, 42
        )


def test_set_string_value():
    mock_key = mock.Mock()
    
    with mock.patch("winreg.SetValueEx") as mock_set:
        arputils._set_value(mock_key, "TestStr", "hello")
        mock_set.assert_called_once_with(
            mock_key, "TestStr", None, winreg.REG_SZ, "hello"
        )


def test_set_path_value_converts_to_string():
    mock_key = mock.Mock()
    test_path = Path("C:/test/path")
    
    with mock.patch("winreg.SetValueEx") as mock_set:
        arputils._set_value(mock_key, "TestPath", test_path)
        mock_set.assert_called_once()
        assert isinstance(mock_set.call_args[0][4], str)


def test_self_cmd_uses_cache():
    arputils._self_cmd_cache = Path("C:/cached/pymanager.exe")
    
    result = arputils._self_cmd()
    assert result == Path("C:/cached/pymanager.exe")
    
    arputils._self_cmd_cache = None


def test_self_cmd_raises_when_not_found(monkeypatch, tmp_path):
    arputils._self_cmd_cache = None
    
    monkeypatch.setenv("LocalAppData", str(tmp_path))
    
    windows_apps = tmp_path / "Microsoft" / "WindowsApps"
    windows_apps.mkdir(parents=True)
    
    with mock.patch.dict("sys.modules", {"_winapi": None}):
        with pytest.raises(FileNotFoundError, match="Cannot determine uninstall command"):
            arputils._self_cmd()
    
    arputils._self_cmd_cache = None


def test_iter_keys_with_none():
    result = list(arputils._iter_keys(None))
    assert result == []


def test_iter_keys_stops_on_oserror():
    mock_key = mock.Mock()
    
    with mock.patch("winreg.EnumKey") as mock_enum:
        mock_enum.side_effect = ["key1", OSError()]
        
        result = list(arputils._iter_keys(mock_key))
        assert result == ["key1"]


def test_delete_key_retries_on_permission_error():
    mock_key = mock.Mock()
    
    with mock.patch("winreg.DeleteKey") as mock_delete:
        with mock.patch("time.sleep"):
            mock_delete.side_effect = [
                PermissionError(),
                PermissionError(),
                None
            ]
            
            arputils._delete_key(mock_key, "test_key")
            
            assert mock_delete.call_count == 3


def test_delete_key_ignores_filenotfound():
    mock_key = mock.Mock()
    
    with mock.patch("winreg.DeleteKey") as mock_delete:
        mock_delete.side_effect = FileNotFoundError()
        
        arputils._delete_key(mock_key, "test_key")
