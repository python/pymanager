#include <string>
#include <vector>

#define _WIN32_WINNT _WIN32_WINNT_WIN10
#include <sdkddkver.h>

#define __WRL_CLASSIC_COM__
#include <wrl.h>

#include <pathcch.h>
#include <strsafe.h>

using namespace Microsoft::WRL;

#include "shellext.h"

static HINSTANCE hModule;


#define CLSID_IDLE_COMMAND "{C7E29CB0-9691-4DE8-B72B-6719DDC0B4A1}"
#define CLSID_LAUNCH_COMMAND "{F7209EE3-FC96-40F4-8C3F-4B7D3994370D}"
#define CLSID_COMMAND_ENUMERATOR "{F82C8CD5-A69C-45CC-ADC6-87FC5F4A7429}"
#define CLSID_DRAGDROPSUPPORT "{EAF5E48F-F54A-4A03-824B-CA880772EE20}"

#ifndef _DEBUG
#undef OutputDebugString
#define OutputDebugString(x)
#endif


static const WPARAM DDWM_UPDATEWINDOW = WM_USER + 3;
static const LPCWSTR DRAG_MESSAGE = L"Open with %1";


LRESULT RegReadStr(HKEY key, LPCWSTR valueName, std::wstring& result)
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


HRESULT ReadIdleInstalls(std::vector<IdleData> &idles, HKEY hkPython, LPCWSTR company, REGSAM flags)
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
            } else {
                err = 0;
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

HRESULT ReadAllIdleInstalls(std::vector<IdleData> &idles, HKEY hive, LPCWSTR root, REGSAM flags)
{
    HKEY hkPython = NULL;
    HRESULT hr = S_OK;
    LSTATUS err = RegOpenKeyExW(hive, root ? root : L"", 0, KEY_READ | flags, &hkPython);

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
    : public RuntimeClass<RuntimeClassFlags<ClassicCom>, IExplorerCommand, IObjectWithSite>
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
        OutputDebugString(L"IdleCommand::Invoke");
        OutputDebugString(exe.c_str());
        OutputDebugString(parameters.c_str());
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

    // IObjectWithSite
private:
    ComPtr<IUnknown> _site;

public:
    IFACEMETHODIMP GetSite(REFIID riid, void **ppvSite)
    {
        if (_site) {
            return _site->QueryInterface(riid, ppvSite);
        }
        *ppvSite = NULL;
        return E_FAIL;
    }

    IFACEMETHODIMP SetSite(IUnknown *pSite)
    {
        _site = pSite;
        return S_OK;
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


class PyManagerOperationInProgress
{
    HANDLE hGlobalSem;
    bool busy;

    bool _create() {
        hGlobalSem = CreateSemaphoreExW(NULL, 0, 1,
            L"PyManager-OperationInProgress", 0, SEMAPHORE_MODIFY_STATE | SYNCHRONIZE);

        return (hGlobalSem && GetLastError() != ERROR_ALREADY_EXISTS);
    }

public:
    PyManagerOperationInProgress()
    {
        busy = _create();
    }

    ~PyManagerOperationInProgress()
    {
        if (hGlobalSem) {
            if (!busy) {
                ReleaseSemaphore(hGlobalSem, 1, NULL);
            }
            CloseHandle(hGlobalSem);
        }
    }

    operator bool()
    {
        return hGlobalSem && !busy;
    }
};


class DECLSPEC_UUID(CLSID_IDLE_COMMAND) IdleCommand
    : public RuntimeClass<RuntimeClassFlags<ClassicCom>, IExplorerCommand, IObjectWithSite>
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

        hr = ReadAllIdleInstalls(idles, HKEY_LOCAL_MACHINE, L"Software\\Python", KEY_WOW64_32KEY);
        if (SUCCEEDED(hr)) {
            hr = ReadAllIdleInstalls(idles, HKEY_LOCAL_MACHINE, L"Software\\Python", KEY_WOW64_64KEY);
        }
        if (SUCCEEDED(hr)) {
            hr = ReadAllIdleInstalls(idles, HKEY_CURRENT_USER, L"Software\\Python", 0);
        }

        if (FAILED(hr)) {
            wchar_t buffer[512];
            swprintf_s(buffer, L"IdleCommand error 0x%08X", (DWORD)hr);
            OutputDebugString(buffer);
            idles.clear();
        }
    }

    #ifdef PYSHELLEXT_TEST
    IdleCommand(HKEY hive, LPCWSTR root) : title(L"Edit in &IDLE")
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

        hr = ReadAllIdleInstalls(idles, hive, root, 0);

        if (FAILED(hr)) {
            idles.clear();
        }
    }
    #endif

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
        if (title.empty()) {
            *pCmdState = ECS_HIDDEN;
            return S_OK;
        }
        *pCmdState = idles.size() ? ECS_ENABLED : ECS_DISABLED;
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

    // IObjectWithSite
private:
    ComPtr<IUnknown> _site;

public:
    IFACEMETHODIMP GetSite(REFIID riid, void **ppvSite)
    {
        if (_site) {
            return _site->QueryInterface(riid, ppvSite);
        }
        *ppvSite = NULL;
        return E_FAIL;
    }

    IFACEMETHODIMP SetSite(IUnknown *pSite)
    {
        _site = pSite;
        return S_OK;
    }
};


class DECLSPEC_UUID(CLSID_DRAGDROPSUPPORT) DragDropSupport : public RuntimeClass<
    RuntimeClassFlags<ClassicCom>, IDropTarget, IPersistFile>
{
    std::wstring target, target_name, target_dir;
    DWORD target_mode;

    static CLIPFORMAT cfDropDescription;
    static CLIPFORMAT cfDragWindow;

    IDataObject *data_obj;

public:
    DragDropSupport() : data_obj(NULL) {
        if (!cfDropDescription) {
            cfDropDescription = RegisterClipboardFormat(CFSTR_DROPDESCRIPTION);
        }
        if (!cfDropDescription) {
            OutputDebugString(L"PyShellExt::DllMain - failed to get CFSTR_DROPDESCRIPTION format");
        }
        if (!cfDragWindow) {
            cfDragWindow = RegisterClipboardFormat(L"DragWindow");
        }
        if (!cfDragWindow) {
            OutputDebugString(L"PyShellExt::DllMain - failed to get DragWindow format");
        }
    }

    ~DragDropSupport() {
        if (data_obj) {
            data_obj->Release();
        }
    }

    HRESULT UpdateDropDescription(DROPDESCRIPTION *drop_desc) {
        StringCchCopy(drop_desc->szMessage, sizeof(drop_desc->szMessage) / sizeof(drop_desc->szMessage[0]), DRAG_MESSAGE);
        StringCchCopy(drop_desc->szInsert, sizeof(drop_desc->szInsert) / sizeof(drop_desc->szInsert[0]), target_name.c_str());
        drop_desc->type = DROPIMAGE_MOVE;
        return S_OK;
    }

    HRESULT UpdateDropDescription(IDataObject *pDataObj) {
        STGMEDIUM medium;
        FORMATETC fmt = {
            cfDropDescription,
            NULL,
            DVASPECT_CONTENT,
            -1,
            TYMED_HGLOBAL
        };

        auto hr = pDataObj->GetData(&fmt, &medium);
        if (FAILED(hr)) {
            OutputDebugString(L"PyShellExt::DragDropSupport::UpdateDropDescription - failed to get DROPDESCRIPTION format");
            return hr;
        }
        if (!medium.hGlobal) {
            OutputDebugString(L"PyShellExt::DragDropSupport::UpdateDropDescription - DROPDESCRIPTION format had NULL hGlobal");
            ReleaseStgMedium(&medium);
            return E_FAIL;
        }
        auto drop_desc = (DROPDESCRIPTION*)GlobalLock(medium.hGlobal);
        if (!drop_desc) {
            OutputDebugString(L"PyShellExt::DragDropSupport::UpdateDropDescription - failed to lock DROPDESCRIPTION hGlobal");
            ReleaseStgMedium(&medium);
            return E_FAIL;
        }
        hr = UpdateDropDescription(drop_desc);

        GlobalUnlock(medium.hGlobal);
        ReleaseStgMedium(&medium);

        return hr;
    }

    HRESULT GetDragWindow(IDataObject *pDataObj, HWND *phWnd) {
        HRESULT hr;
        HWND *pMem;
        STGMEDIUM medium;
        FORMATETC fmt = {
            cfDragWindow,
            NULL,
            DVASPECT_CONTENT,
            -1,
            TYMED_HGLOBAL
        };

        hr = pDataObj->GetData(&fmt, &medium);
        if (FAILED(hr)) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetDragWindow - failed to get DragWindow format");
            return hr;
        }
        if (!medium.hGlobal) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetDragWindow - DragWindow format had NULL hGlobal");
            ReleaseStgMedium(&medium);
            return E_FAIL;
        }

        pMem = (HWND*)GlobalLock(medium.hGlobal);
        if (!pMem) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetDragWindow - failed to lock DragWindow hGlobal");
            ReleaseStgMedium(&medium);
            return E_FAIL;
        }

        *phWnd = *pMem;

        GlobalUnlock(medium.hGlobal);
        ReleaseStgMedium(&medium);

        return S_OK;
    }

    HRESULT GetArgumentsW(LPCWSTR files, LPCWSTR *pArguments) {
        std::wstring arg_str;
        while (arg_str.size() < 32767 && *files) {
            std::wstring wfile(files);
            files += wfile.size() + 1;

            if (wfile.find(L' ') != wfile.npos) {
                wfile.insert(wfile.begin(), L'"');
                wfile.push_back(L'"');
            }
            if (arg_str.size()) {
                arg_str.push_back(L' ');
            }
            arg_str += wfile;
        }

        LPWSTR args = (LPWSTR)CoTaskMemAlloc(sizeof(WCHAR) * (arg_str.size() + 1));
        *pArguments = args;
        if (!args) {
            return E_OUTOFMEMORY;
        }
        wcscpy_s(args, arg_str.size() + 1, arg_str.c_str());

        return S_OK;
    }

    HRESULT GetArgumentsA(LPCSTR files, LPCWSTR *pArguments) {
        std::string arg_str;
        while (arg_str.size() < 32767 && *files) {
            std::string file(files);
            files += file.size() + 1;

            if (file.find(' ') != file.npos) {
                file.insert(file.begin(), '"');
                file.push_back('"');
            }
            if (arg_str.size()) {
                arg_str.push_back(' ');
            }
            arg_str += file;
        }

        int wlen = MultiByteToWideChar(CP_ACP, 0, arg_str.data(), arg_str.size(), NULL, 0);
        if (!wlen) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetArguments - failed to get length of wide-char path");
            return E_FAIL;
        }

        LPWSTR args = (LPWSTR)CoTaskMemAlloc(sizeof(WCHAR) * (wlen + 1));
        if (!args) {
            return E_OUTOFMEMORY;
        }
        wlen = MultiByteToWideChar(CP_ACP, 0, arg_str.data(), arg_str.size(), args, wlen + 1);
        if (!wlen) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetArguments - failed to convert multi-byte to wide-char path");
            CoTaskMemFree(args);
            return E_FAIL;
        }
        args[wlen] = '\0';
        *pArguments = args;
        return S_OK;
    }

    HRESULT GetArguments(IDataObject *pDataObj, LPCWSTR *pArguments) {
        HRESULT hr;
        DROPFILES *pdropfiles;

        STGMEDIUM medium;
        FORMATETC fmt = {
            CF_HDROP,
            NULL,
            DVASPECT_CONTENT,
            -1,
            TYMED_HGLOBAL
        };

        hr = pDataObj->GetData(&fmt, &medium);
        if (FAILED(hr)) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetArguments - failed to get CF_HDROP format");
            return hr;
        }
        if (!medium.hGlobal) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetArguments - CF_HDROP format had NULL hGlobal");
            ReleaseStgMedium(&medium);
            return E_FAIL;
        }

        pdropfiles = (DROPFILES*)GlobalLock(medium.hGlobal);
        if (!pdropfiles) {
            OutputDebugString(L"PyShellExt::DragDropSupport::GetArguments - failed to lock CF_HDROP hGlobal");
            ReleaseStgMedium(&medium);
            return E_FAIL;
        }

        if (pdropfiles->fWide) {
            LPCWSTR files = (LPCWSTR)((char*)pdropfiles + pdropfiles->pFiles);
            hr = GetArgumentsW(files, pArguments);
        } else {
            LPCSTR files = (LPCSTR)((char*)pdropfiles + pdropfiles->pFiles);
            hr = GetArgumentsA(files, pArguments);
        }

        GlobalUnlock(medium.hGlobal);
        ReleaseStgMedium(&medium);

        return hr;
    }

    HRESULT NotifyDragWindow(HWND hwnd) {
        LRESULT res;

        if (!hwnd) {
            return S_FALSE;
        }

        res = SendMessage(hwnd, DDWM_UPDATEWINDOW, 0, NULL);

        if (res) {
            OutputDebugString(L"PyShellExt::DragDropSupport::NotifyDragWindow - failed to post DDWM_UPDATEWINDOW");
            return E_FAIL;
        }

        return S_OK;
    }

    // IDropTarget implementation

    STDMETHODIMP DragEnter(IDataObject *pDataObj, DWORD grfKeyState, POINTL pt, DWORD *pdwEffect) {
        HWND hwnd;

        OutputDebugString(L"PyShellExt::DragDropSupport::DragEnter");

        pDataObj->AddRef();
        data_obj = pDataObj;

        *pdwEffect = DROPEFFECT_MOVE;

        if (FAILED(UpdateDropDescription(data_obj))) {
            OutputDebugString(L"PyShellExt::DragDropSupport::DragEnter - failed to update drop description");
        }
        if (FAILED(GetDragWindow(data_obj, &hwnd))) {
            OutputDebugString(L"PyShellExt::DragDropSupport::DragEnter - failed to get drag window");
        }
        if (FAILED(NotifyDragWindow(hwnd))) {
            OutputDebugString(L"PyShellExt::DragDropSupport::DragEnter - failed to notify drag window");
        }

        return S_OK;
    }

    STDMETHODIMP DragLeave() {
        return S_OK;
    }

    STDMETHODIMP DragOver(DWORD grfKeyState, POINTL pt, DWORD *pdwEffect) {
        return S_OK;
    }

    STDMETHODIMP Drop(IDataObject *pDataObj, DWORD grfKeyState, POINTL pt, DWORD *pdwEffect) {
        LPCWSTR args;

        OutputDebugString(L"PyShellExt::DragDropSupport::Drop");
        *pdwEffect = DROPEFFECT_NONE;

        if (pDataObj != data_obj) {
            OutputDebugString(L"PyShellExt::DragDropSupport::Drop - unexpected data object");
            return E_FAIL;
        }

        data_obj->Release();
        data_obj = NULL;

        if (SUCCEEDED(GetArguments(pDataObj, &args))) {
            OutputDebugString(args);
            ShellExecute(NULL, NULL, target.c_str(), args, target_dir.c_str(), SW_NORMAL);

            CoTaskMemFree((LPVOID)args);
        } else {
            OutputDebugString(L"PyShellExt::DragDropSupport::Drop - failed to get launch arguments");
        }

        return S_OK;
    }

    // IPersistFile implementation

    STDMETHODIMP GetCurFile(LPOLESTR *ppszFileName) {
        HRESULT hr;
        size_t len = target.size();

        if (!ppszFileName) {
            return E_POINTER;
        }

        *ppszFileName = (LPOLESTR)CoTaskMemAlloc(sizeof(WCHAR) * (len + 1));
        if (!*ppszFileName) {
            return E_OUTOFMEMORY;
        }

        hr = StringCchCopy(*ppszFileName, len + 1, target.c_str());
        if (FAILED(hr)) {
            CoTaskMemFree(*ppszFileName);
            *ppszFileName = NULL;
            return E_FAIL;
        }

        return S_OK;
    }

    STDMETHODIMP IsDirty() {
        return S_FALSE;
    }

    STDMETHODIMP Load(LPCOLESTR pszFileName, DWORD dwMode) {
        OutputDebugString(L"PyShellExt::DragDropSupport::Load");
        OutputDebugString(pszFileName);

        target = pszFileName;
        target_dir = pszFileName;
        switch (PathCchRemoveFileSpec(target_dir.data(), target_dir.size())) {
        case S_OK:
            target_dir.resize(wcsnlen_s(target_dir.data(), target_dir.size()));
            target_name = { target.begin() + target_dir.size(), target.end() };
            while (!target_name.empty() && (target_name.front() == L'\\' || target_name.front() == L'/')) {
                target_name.erase(0, 1);
            }
            break;
        case S_FALSE:
            target_name = L"script";
            break;
        default:
            OutputDebugString(L"PyShellExt::DragDropSupport::Load - failed to remove filespec from target");
            return E_FAIL;
        }

        OutputDebugString(target.c_str());
        target_mode = dwMode;
        OutputDebugString(L"PyShellExt::DragDropSupport::Load - S_OK");
        return S_OK;
    }

    STDMETHODIMP Save(LPCOLESTR pszFileName, BOOL fRemember) {
        return E_NOTIMPL;
    }

    STDMETHODIMP SaveCompleted(LPCOLESTR pszFileName) {
        return E_NOTIMPL;
    }

    STDMETHODIMP GetClassID(CLSID *pClassID) {
        *pClassID = __uuidof(DragDropSupport);
        return S_OK;
    }
};

CLIPFORMAT DragDropSupport::cfDropDescription = 0;
CLIPFORMAT DragDropSupport::cfDragWindow = 0;


CoCreatableClass(IdleCommand);
CoCreatableClass(DragDropSupport);


#ifdef PYSHELLEXT_TEST

IExplorerCommand *MakeLaunchCommand(std::wstring title, std::wstring exe, std::wstring idle)
{
    IdleData data = { .title = title, .exe = exe, .idle = idle };
    return Make<LaunchCommand>(data).Detach();
}


IExplorerCommand *MakeIdleCommand(HKEY hive, LPCWSTR root)
{
    return Make<IdleCommand>(hive, root).Detach();
}

HRESULT GetDropArgumentsW(LPCWSTR args, std::wstring &parsed)
{
    LPCWSTR p;
    auto o = Make<DragDropSupport>();
    HRESULT hr = o->GetArgumentsW(args, &p);
    if (SUCCEEDED(hr)) {
        parsed = p;
        CoTaskMemFree((LPVOID)p);
    }
    return hr;
}

HRESULT GetDropArgumentsA(LPCSTR args, std::wstring &parsed)
{
    LPCWSTR p;
    auto o = Make<DragDropSupport>();
    HRESULT hr = o->GetArgumentsA(args, &p);
    if (SUCCEEDED(hr)) {
        parsed = p;
        CoTaskMemFree((LPVOID)p);
    }
    return hr;
}

HRESULT GetDropDescription(LPCOLESTR pszFileName, DWORD dwMode, std::wstring &message, std::wstring &insert)
{
    auto o = Make<DragDropSupport>();
    HRESULT hr = o->Load(pszFileName, dwMode);
    if (FAILED(hr)) {
        return hr;
    }
    DROPDESCRIPTION drop_desc;
    ZeroMemory(&drop_desc, sizeof(drop_desc));
    hr = o->UpdateDropDescription(&drop_desc);
    if (SUCCEEDED(hr)) {
        message = drop_desc.szMessage;
        insert = drop_desc.szInsert;
    }
    return hr;
}

#elif defined(_WINDLL)

STDAPI DllGetClassObject(REFCLSID rclsid, REFIID riid, _COM_Outptr_ void** ppv)
{
    return Module<InProc>::GetModule().GetClassObject(rclsid, riid, ppv);
}


STDAPI DllCanUnloadNow()
{
    return Module<InProc>::GetModule().Terminate() ? S_OK : S_FALSE;
}

STDAPI_(BOOL) DllMain(_In_opt_ HINSTANCE hinst, DWORD reason, _In_opt_ void*)
{
    if (reason == DLL_PROCESS_ATTACH) {
        hModule = hinst;
        DisableThreadLibraryCalls(hinst);
    }
    return TRUE;
}

#else

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

#endif
