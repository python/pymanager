#pragma once

#include <windows.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <olectl.h>

#include <string>
#include <vector>

LRESULT RegReadStr(HKEY key, LPCWSTR valueName, std::wstring& result);

struct IdleData {
    std::wstring title;
    std::wstring exe;
    std::wstring idle;
};

HRESULT ReadIdleInstalls(std::vector<IdleData> &idles, HKEY hkPython, LPCWSTR company, REGSAM flags);
HRESULT ReadAllIdleInstalls(std::vector<IdleData> &idles, HKEY hive, LPCWSTR root, REGSAM flags);

IExplorerCommand *MakeIdleCommand(HKEY hive, LPCWSTR root);
IExplorerCommand *MakeLaunchCommand(std::wstring title, std::wstring exe, std::wstring idle);
HRESULT GetDropArgumentsW(LPCWSTR args, std::wstring &parsed);
HRESULT GetDropArgumentsA(LPCSTR args, std::wstring &parsed);
HRESULT GetDropDescription(LPCOLESTR pszFileName, DWORD dwMode, std::wstring &message, std::wstring &insert);
