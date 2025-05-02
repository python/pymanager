#define _WIN32_WINNT _WIN32_WINNT_WIN10
#include <sdkddkver.h>

#define __WRL_CLASSIC_COM__
#include <wrl.h>

using namespace Microsoft::WRL;

#include <windows.h>
#include <shlobj.h>
#include <shlwapi.h>
#include <olectl.h>

#include <string>
#include <vector>

static HINSTANCE hModule;

#define CLSID_IDLE_COMMAND "{C7E29CB0-9691-4DE8-B72B-6719DDC0B4A1}"
#define CLSID_LAUNCH_COMMAND "{F7209EE3-FC96-40F4-8C3F-4B7D3994370D}"
#define CLSID_COMMAND_ENUMERATOR "{F82C8CD5-A69C-45CC-ADC6-87FC5F4A7429}"


struct IdleData {
    std::wstring title;
    std::wstring exe;
    std::wstring idle;
};


static LRESULT RegReadStr(HKEY key, LPCWSTR valueName, std::wstring& result)
{
    DWORD reg_type;
    while (true) {
        DWORD cch = result.size() * sizeof(result[0]);
        LRESULT err = RegQueryValueEx(key, valueName, NULL, &reg_type,
                                      (LPBYTE)result.data(), &cch);
        cch /= sizeof(result[0]);
        if (err == ERROR_SUCCESS && reg_type == REG_SZ) {
            result.resize(cch);
            while (!result.empty() && result.back() == L'\0') {
                result.pop_back();
            }
            return err;
        }
        if (err && err != ERROR_MORE_DATA) {
            return err;
        }
        if (reg_type != REG_SZ) {
            return ERROR_INVALID_DATA;
        }
        if (cch <= result.size()) {
            return err;
        }
        result.resize(cch);
    }
}


static HRESULT ReadIdleInstalls(std::vector<IdleData> &idles, HKEY hkPython, LPCWSTR company, REGSAM flags)
{
    HKEY hkCompany = NULL, hkTag = NULL, hkInstall = NULL;
    LSTATUS err = RegOpenKeyExW(
        hkPython,
        company,
        0,
        KEY_READ | flags,
        &hkCompany
    );

    for (DWORD i = 0; !err && i < 64; ++i) {
        wchar_t name[512];
        DWORD cchName = sizeof(name) / sizeof(name[0]);
        err = RegEnumKeyExW(hkCompany, i, name, &cchName, NULL, NULL, NULL, NULL);
        if (!err) {
            err = RegOpenKeyExW(hkCompany, name, 0, KEY_READ | flags, &hkTag);
        }
        if (!err) {
            err = RegOpenKeyExW(hkTag, L"InstallPath", 0, KEY_READ | flags, &hkInstall);
        }
        if (err) {
            break;
        }

        IdleData data;

        err = RegReadStr(hkTag, L"DisplayName", data.title);
        if (err) {
            data.title = std::wstring(L"Python ") + name;
        }

        err = RegReadStr(hkInstall, L"WindowedExecutablePath", data.exe);
        if (err == ERROR_FILE_NOT_FOUND || err == ERROR_INVALID_DATA) {
            err = RegReadStr(hkInstall, L"ExecutablePath", data.exe);
            if (err == ERROR_FILE_NOT_FOUND || err == ERROR_INVALID_DATA) {
                err = RegReadStr(hkInstall, NULL, data.exe);
                if (!err) {
                    if (data.exe.back() != L'\\') {
                        data.exe += L"\\python.exe";
                    } else {
                        data.exe += L"python.exe";
                    }
                }
            }
        }
        if (err) {
            break;
        }

        err = RegReadStr(hkInstall, L"IdlePath", data.idle);
        if (err == ERROR_FILE_NOT_FOUND || err == ERROR_INVALID_DATA) {
            if (0 == wcsicmp(company, L"PythonCore")) {
                // Only use fallback logic for PythonCore
                err = RegReadStr(hkInstall, NULL, data.idle);
                if (!err) {
                    if (data.idle.back() != L'\\') {
                        data.idle += L"\\Lib\\idlelib\\idle.pyw";
                    } else {
                        data.idle += L"Lib\\idlelib\\idle.pyw";
                    }
                }
            }
        }
        if (err) {
            break;
        }

        RegCloseKey(hkInstall);
        hkInstall = NULL;
        RegCloseKey(hkTag);
        hkTag = NULL;

        if (!data.exe.empty()
            && !data.idle.empty()
            && GetFileAttributesW(data.exe.c_str()) != INVALID_FILE_ATTRIBUTES
            && GetFileAttributesW(data.idle.c_str()) != INVALID_FILE_ATTRIBUTES) {
            idles.push_back(data);
        }
    }
    if (hkInstall) {
        RegCloseKey(hkInstall);
    }
    if (hkTag) {
        RegCloseKey(hkTag);
    }
    if (hkCompany) {
        RegCloseKey(hkCompany);
    }
    if (err && err != ERROR_NO_MORE_ITEMS && err != ERROR_FILE_NOT_FOUND) {
        return HRESULT_FROM_WIN32(err);
    }
    return S_OK;
}

static HRESULT ReadAllIdleInstalls(std::vector<IdleData> &idles, HKEY hive, REGSAM flags)
{
    HKEY hkPython = NULL;
    HRESULT hr = S_OK;
    LSTATUS err = RegOpenKeyExW(hive, L"Software\\Python", 0, KEY_READ | flags, &hkPython);

    for (DWORD i = 0; !err && hr == S_OK && i < 64; ++i) {
        wchar_t name[512];
        DWORD cchName = sizeof(name) / sizeof(name[0]);
        err = RegEnumKeyExW(hkPython, i, name, &cchName, NULL, NULL, NULL, NULL);
        if (!err) {
            hr = ReadIdleInstalls(idles, hkPython, name, flags);
        }
    }

    if (hkPython) {
        RegCloseKey(hkPython);
    }

    if (err && err != ERROR_NO_MORE_ITEMS && err != ERROR_FILE_NOT_FOUND) {
        return HRESULT_FROM_WIN32(err);
    }
    return hr;
}

class DECLSPEC_UUID(CLSID_LAUNCH_COMMAND) LaunchCommand
    : public RuntimeClass<RuntimeClassFlags<ClassicCom>, IExplorerCommand>
{
    std::wstring title;
    std::wstring exe;
    std::wstring idle;
public:
    LaunchCommand(const IdleData &data) : title(data.title), exe(data.exe), idle(data.idle)
    { }

    // IExplorerCommand
    IFACEMETHODIMP GetTitle(IShellItemArray *psiItemArray, LPWSTR *ppszName)
    {
        *ppszName = (LPWSTR)CoTaskMemAlloc((title.size() + 1) * sizeof(WCHAR));
        wcscpy_s(*ppszName, title.size() + 1, title.data());
        return S_OK;
    }

    IFACEMETHODIMP GetIcon(IShellItemArray *psiItemArray, LPWSTR *ppszIcon)
    {
        *ppszIcon = NULL;
        return E_NOTIMPL;
    }

    IFACEMETHODIMP GetToolTip(IShellItemArray *psiItemArray, LPWSTR *ppszInfotip)
    {
        *ppszInfotip = NULL;
        return E_NOTIMPL;
    }

    IFACEMETHODIMP GetCanonicalName(GUID* pguidCommandName)
    {
        *pguidCommandName = __uuidof(LaunchCommand);
        return S_OK;
    }

    IFACEMETHODIMP GetState(IShellItemArray *psiItemArray, BOOL fOkToBeSlow, EXPCMDSTATE *pCmdState)
    {
        *pCmdState = ECS_ENABLED;
        return S_OK;
    }

    IFACEMETHODIMP Invoke(IShellItemArray *psiItemArray, IBindCtx *pbc)
    {
        std::wstring parameters;
        if (idle.find(L' ') != idle.npos) {
            parameters = L"\"" + idle + L"\"";
        } else {
            parameters = idle;
        }

        HRESULT hr;
        DWORD count;
        psiItemArray->GetCount(&count);
        for (DWORD i = 0; i < count; ++i) {
            PWSTR path;
            IShellItem *psi;
            hr = psiItemArray->GetItemAt(0, &psi);
            if (FAILED(hr))
                continue;
            hr = psi->GetDisplayName(SIGDN_FILESYSPATH, &path);
            psi->Release();
            if (FAILED(hr))
                continue;

            if (wcschr(path, L' ')) {
                parameters += L" \"";
                parameters += path;
                parameters += L"\"";
            } else {
                parameters += L" ";
                parameters += path;
            }
            CoTaskMemFree(path);
        }

        SHELLEXECUTEINFOW sei = {
            sizeof(SHELLEXECUTEINFOW),
            SEE_MASK_NO_CONSOLE | SEE_MASK_NOASYNC,
            NULL,
            NULL,
            exe.c_str(),
            parameters.c_str(),
            NULL
        };
        OutputDebugStringW(L"IdleCommand::Invoke");
        OutputDebugStringW(exe.c_str());
        OutputDebugStringW(parameters.c_str());
        ShellExecuteExW(&sei);
        return S_OK;
    }

    IFACEMETHODIMP GetFlags(EXPCMDFLAGS *pFlags)
    {
        *pFlags = ECF_DEFAULT;
        return S_OK;
    }

    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand **ppEnum)
    {
        *ppEnum = NULL;
        return E_NOTIMPL;
    }
};


class DECLSPEC_UUID(CLSID_COMMAND_ENUMERATOR) CommandEnumerator
    : public RuntimeClass<RuntimeClassFlags<ClassicCom>, IEnumExplorerCommand>
{
    std::vector<IdleData> idles;
    size_t index;
public:
    CommandEnumerator(std::vector<IdleData> idles, size_t index)
        : idles(idles), index(index) { }

    IFACEMETHODIMP Clone(IEnumExplorerCommand **ppenum)
    {
        return Make<CommandEnumerator>(idles, index)
            ->QueryInterface(IID_IEnumExplorerCommand, (void **)ppenum);
    }

    IFACEMETHODIMP Next(ULONG celt, IExplorerCommand **pUICommand, ULONG *pceltFetched)
    {
        ULONG c = 0;
        while (celt-- && index < idles.size()) {
            *pUICommand = Make<LaunchCommand>(idles[index]).Detach();
            index += 1;
            c += 1;
        }
        if (pceltFetched) {
            *pceltFetched = c;
        }
        return c ? S_OK : S_FALSE;
    }

    IFACEMETHODIMP Reset()
    {
        index = 0;
        return S_OK;
    }

    IFACEMETHODIMP Skip(ULONG celt)
    {
        index += celt;
        return S_OK;
    }
};


class DECLSPEC_UUID(CLSID_IDLE_COMMAND) IdleCommand
    : public RuntimeClass<RuntimeClassFlags<ClassicCom>, IExplorerCommand>
{
    std::vector<IdleData> idles;
    std::wstring iconPath;
    std::wstring title;
public:
    IdleCommand() : title(L"Edit in &IDLE")
    {
        HRESULT hr;

        DWORD cch = 260;
        while (iconPath.size() < cch) {
            iconPath.resize(cch);
            cch = GetModuleFileNameW(hModule, iconPath.data(), iconPath.size());
        }
        iconPath.resize(cch);
        if (cch) {
            iconPath += L",-4";
        }

        hr = ReadAllIdleInstalls(idles, HKEY_LOCAL_MACHINE, KEY_WOW64_32KEY);
        if (SUCCEEDED(hr)) {
            hr = ReadAllIdleInstalls(idles, HKEY_LOCAL_MACHINE, KEY_WOW64_64KEY);
        }
        if (SUCCEEDED(hr)) {
            hr = ReadAllIdleInstalls(idles, HKEY_CURRENT_USER, 0);
        }

        if (FAILED(hr)) {
            wchar_t buffer[512];
            swprintf_s(buffer, L"IdleCommand error 0x%08X", (DWORD)hr);
            OutputDebugStringW(buffer);
            idles.clear();
        }
    }

    // IExplorerCommand
    IFACEMETHODIMP GetTitle(IShellItemArray *psiItemArray, LPWSTR *ppszName)
    {
        *ppszName = (LPWSTR)CoTaskMemAlloc((title.size() + 1) * sizeof(WCHAR));
        wcscpy_s(*ppszName, title.size() + 1, title.c_str());
        return S_OK;
    }

    IFACEMETHODIMP GetIcon(IShellItemArray *psiItemArray, LPWSTR *ppszIcon)
    {
        if (!iconPath.empty()) {
            *ppszIcon = (LPWSTR)CoTaskMemAlloc((iconPath.size() + 1) * sizeof(WCHAR));
            wcscpy_s(*ppszIcon, iconPath.size() + 1, iconPath.c_str());
            return S_OK;
        } else {
            *ppszIcon = NULL;
            return E_NOTIMPL;
        }
    }

    IFACEMETHODIMP GetToolTip(IShellItemArray *psiItemArray, LPWSTR *ppszInfotip)
    {
        *ppszInfotip = NULL;
        return E_NOTIMPL;
    }

    IFACEMETHODIMP GetCanonicalName(GUID* pguidCommandName)
    {
        *pguidCommandName = __uuidof(IdleCommand);
        return S_OK;
    }

    IFACEMETHODIMP GetState(IShellItemArray *psiItemArray, BOOL fOkToBeSlow, EXPCMDSTATE *pCmdState)
    {
        *pCmdState = idles.size() ? ECS_ENABLED : ECS_HIDDEN;
        return S_OK;
    }

    IFACEMETHODIMP Invoke(IShellItemArray *psiItemArray, IBindCtx *pbc)
    {
        return E_NOTIMPL;
    }

    IFACEMETHODIMP GetFlags(EXPCMDFLAGS *pFlags)
    {
        *pFlags = ECF_HASSUBCOMMANDS;
        return S_OK;
    }

    IFACEMETHODIMP EnumSubCommands(IEnumExplorerCommand **ppEnum)
    {
        *ppEnum = Make<CommandEnumerator>(
            std::vector<IdleData>{std::rbegin(idles), std::rend(idles)},
            0
        ).Detach();
        return S_OK;
    }
};


CoCreatableClass(IdleCommand);


class OutOfProcModule : public Module<OutOfProc, OutOfProcModule>
{ };


int WINAPI wWinMain(
    HINSTANCE hInstance,
    HINSTANCE hPrevInstance,
    LPWSTR lpCmdLine,
    int nCmdShow
)
{
    HANDLE hStopEvent = CreateEvent(NULL, TRUE, FALSE, NULL);
    hModule = hInstance;

    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    auto& module = OutOfProcModule::Create([=]() { SetEvent(hStopEvent); });
    module.RegisterObjects();
    ::WaitForSingleObject(hStopEvent, INFINITE);
    module.UnregisterObjects();
    CoUninitialize();
    return 0;
}

