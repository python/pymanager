#include <windows.h>
#include <stdio.h>

#include "_launch.h"

#define MAXLEN 32768

// HRESULT-compatible error codes
#define ERROR_RELATIVE_PATH     0xA0000001
#define ERROR_NO_PYTHON3        0xA0000002
#define ERROR_DLL_LOAD_DISABLED 0xA0000003

static int
print_error(int err, const wchar_t *message)
{
    DWORD len;
    wchar_t *os_message;

    if (!err) {
        err = GetLastError();
    }
    if ((err & 0xFFFF0000) == 0x80070000) {
        // extract Win32 error code from HRESULT
        err = err & 0xFFFF;
    }

    switch (err) {
    case 0:
        fwprintf(stderr, L"[WARN] Error was reported but no error code was set.\n"
                        "[ERROR] %s\n", message);
        break;
    case ERROR_RELATIVE_PATH:
        fwprintf(stderr, L"[ERROR] %s: an absolute path is required.\n", message);
        break;
    case ERROR_NO_PYTHON3:
        fwprintf(stderr, L"[ERROR] %s: python3.dll is not found.\n", message);
        break;
    case ERROR_DLL_LOAD_DISABLED:
        fwprintf(stderr, L"[ERROR] %s: DLL loading is disabled.\n", message);
        break;
    case ERROR_INVALID_FUNCTION:
    case ERROR_ACCESS_DENIED:
        fwprintf(stderr,
                 L"[ERROR] %s: "
                 L"the install path could not be accessed (0x%04X).\n"
                 L"Try 'py install --repair <version>' to reinstall.\n",
                 message, err);
        break;
    case ERROR_FILE_NOT_FOUND:
    case ERROR_PATH_NOT_FOUND:
    case ERROR_INVALID_DRIVE:
        fwprintf(stderr,
                 L"[ERROR] %s: "
                 L"the install path was not found (0x%04X).\n"
                 L"Try 'py install --repair <version>' to reinstall.\n",
                 message, err);
        break;
    case ERROR_EXE_MACHINE_TYPE_MISMATCH:
        fwprintf(stderr,
                 L"[ERROR] %s: "
                 L"the runtime is for a different machine architecture (0x%04X).\n"
                 L"Use 'py install <version>' to install a different platform.\n",
                 message, err);
        break;
    case ERROR_BAD_FORMAT:
    case ERROR_MOD_NOT_FOUND:
    case ERROR_PROC_NOT_FOUND:
    case ERROR_INVALID_STARTING_CODESEG:
    case ERROR_INVALID_STACKSEG:
    case ERROR_INVALID_MODULETYPE:
    case ERROR_INVALID_EXE_SIGNATURE:
    case ERROR_EXE_MARKED_INVALID:
    case ERROR_BAD_EXE_FORMAT:
        fwprintf(stderr,
                 L"[ERROR] %s: "
                 L"the executable is corrupt or invalid (0x%08X).\n"
                 L"Try 'py install --repair <version>' to reinstall.\n",
                 message, err);
        break;
    case ERROR_NOT_ENOUGH_MEMORY:
    case ERROR_OUTOFMEMORY:
        fwprintf(stderr, L"[ERROR] %s: the system is out of memory (0x%04X).\n",
                 message, err);
        break;
    default:
        len = FormatMessageW(
            FORMAT_MESSAGE_ALLOCATE_BUFFER
            | FORMAT_MESSAGE_FROM_SYSTEM
            | FORMAT_MESSAGE_IGNORE_INSERTS,
            NULL,
            err,
            MAKELANGID(LANG_NEUTRAL, SUBLANG_DEFAULT),
            (LPWSTR)&os_message,
            0,
            NULL
        );
        if (len) {
            while (len > 0 && isspace(os_message[--len])) {
                os_message[len] = L'\0';
            }
            fwprintf(stderr, L"[ERROR] %s: %s (0x%08X)\n", message, os_message, err);
            LocalFree((void *)os_message);
        } else {
            fwprintf(stderr, L"[ERROR] %s (0x%08X)\n", message, err);
        }
    }
    return err;
}


int
get_executable(wchar_t *executable, unsigned int bufferSize)
{
    wchar_t config[MAXLEN];
    DWORD len = GetModuleFileNameW(NULL, config, MAXLEN);
    if (len == 0) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    wcscat_s(config, MAXLEN, L".__target__");

    HANDLE hFile = CreateFileW(config, GENERIC_READ,
        FILE_SHARE_READ | FILE_SHARE_DELETE, NULL, OPEN_EXISTING, 0, NULL);
    if (hFile == INVALID_HANDLE_VALUE) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    char buffer[MAXLEN];
    DWORD bytesRead;
    if (!ReadFile(hFile, buffer, sizeof(buffer), &bytesRead, NULL)) {
        int err = GetLastError();
        CloseHandle(hFile);
        return HRESULT_FROM_WIN32(err);
    }
    buffer[bytesRead] = '\0';
    CloseHandle(hFile);
    if (!MultiByteToWideChar(CP_UTF8, 0, buffer, bytesRead + 1, executable, bufferSize)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    return 0;
}


int
get_script(wchar_t **result_path)
{
    HANDLE ph = GetProcessHeap();
    wchar_t *path = NULL;
    DWORD path_len = 0;
    DWORD len = 0;
    int error = 0;
    const wchar_t *SUFFIX = L".__script__.py";

    // Get our path in a dynamic buffer with enough space to add SUFFIX
    while (len >= path_len) {
        if (path) {
            HeapFree(ph, 0, path);
        }
        path_len += 260;

        path = (wchar_t *)HeapAlloc(ph, HEAP_ZERO_MEMORY, sizeof(wchar_t) * path_len);
        if (!path) {
            return HRESULT_FROM_WIN32(GetLastError());
        }

        len = GetModuleFileNameW(NULL, path, path_len - wcslen(SUFFIX));
        if (len == 0) {
            error = GetLastError();
            HeapFree(ph, 0, path);
            return HRESULT_FROM_WIN32(error);
        }
    }

    wcscpy_s(&path[len], path_len - len, SUFFIX);

    // Check that we have a script file. FindFirstFile should be fastest.
    WIN32_FIND_DATAW fd;
    HANDLE fh = FindFirstFileW(path, &fd);
    if (fh == INVALID_HANDLE_VALUE) {
        error = GetLastError();
        HeapFree(ph, 0, path);
        switch (error) {
        case ERROR_INVALID_FUNCTION:
        case ERROR_FILE_NOT_FOUND:
        case ERROR_PATH_NOT_FOUND:
            // This is the typical exit for normal launches. We ought to be nice
            // and fast up until this point, but can be slower through every
            // other path.
            return 0;
        default:
            return HRESULT_FROM_WIN32(error);
        }
    }
    FindClose(fh);

    // Deliberately letting our memory leak - it'll be cleaned up when the
    // process ends, and this is not a loop.
    *result_path = path;
    return 0;
}


int
try_load_python3_dll(const wchar_t *executable, unsigned int bufferSize, void **mainFunction)
{
#ifdef NO_DLL_LOADING
    return ERROR_DLL_LOAD_DISABLED;
#else
    wchar_t directory[MAXLEN];
    wcscpy_s(directory, MAXLEN, executable);
    wchar_t *sep = wcsrchr(directory, L'\\');
    if (!sep) {
        return ERROR_RELATIVE_PATH;
    }
    *sep = L'\0';

    if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32 | LOAD_LIBRARY_SEARCH_USER_DIRS)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    AddDllDirectory(directory);
    HMODULE mod = LoadLibraryExW(L"python3.dll", NULL, 0);
    if (!mod) {
        return GetLastError();
    }
    unsigned long *version = (unsigned long *)GetProcAddress(mod, "Py_Version");
    if (!version || *version < 0x030A0000 || *version >= 0x04000000) {
        FreeLibrary(mod);
        return ERROR_NO_PYTHON3;
    }
    *mainFunction = GetProcAddress(mod, "Py_Main");
    if (!*mainFunction) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    return 0;
#endif
}

static int
launch_by_dll(void *main_func_ptr, wchar_t *executable, int argc, wchar_t **argv, int *exit_code)
{
    int (*main_func)(int argc, wchar_t **argv) = (int (*)(int, wchar_t **))main_func_ptr;

    // We have a Py_Main() to call, so let's create the argv that we need
    wchar_t **newArgv = (wchar_t **)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, argc * sizeof(wchar_t *));
    if (!newArgv) {
        return print_error(0, L"Failed to allocate command line");
    }

    newArgv[0] = executable;
    for (int i = 1; i < argc; ++i) {
        newArgv[i] = argv[i];
    }

    // Our caller assumes that any error result happens before we launch. From
    // this point on, exit_code is set (possibly to an error), and so we should
    // only return 0.

    *exit_code = (*main_func)(argc, newArgv);

    HeapFree(GetProcessHeap(), 0, newArgv);
    return 0;
}

int
wmain(int argc, wchar_t **argv)
{
    int exit_code;
    wchar_t executable[MAXLEN];
    wchar_t *script = NULL;

    int err = get_executable(executable, MAXLEN);
    if (err) {
        return print_error(err, L"Failed to get target path");
    }

    err = get_script(&script);
    if (err) {
        return print_error(err, L"Failed to get script path");
    }

    void *main_func = NULL;
    err = try_load_python3_dll(executable, MAXLEN, (void **)&main_func);
    switch (err) {
    case 0:
        if (script) {
            wchar_t **argv2 = (wchar_t **)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY,
                (argc + 1) * sizeof(wchar_t *));
            if (!argv2) {
                return HRESULT_FROM_WIN32(GetLastError());
            }
            argv2[0] = argv[0];
            argv2[1] = script;
            for (int i = 1; i < argc; ++i) {
                argv2[i + 1] = argv[i];
            }
            argv = argv2;
            argc += 1;
        }
        err = launch_by_dll(main_func, executable, argc, argv, &exit_code);
        if (!err) {
            return exit_code;
        }
        break;
    case ERROR_NO_PYTHON3:
        // expected for incompatible runtimes - fall through to the .exe
        break;
    case ERROR_RELATIVE_PATH:
    case ERROR_DLL_LOAD_DISABLED:
        // specific errors leading to fallthrough
        break;
    default:
        // Errors at non-fatal steps (such as "python3.dll not found") will not
        // have the top bit set.
        if (err > 0 &&
            !GetEnvironmentVariableW(L"PYMANAGER_DEBUG", NULL, 0) &&
            !GetEnvironmentVariableW(L"PYMANAGER_VERBOSE", NULL, 0)) {
            break;
        }
        // Other errors indicate that we ought to have succeeded but didn't, so
        // display a message but still fall back to a regular launch.
        // Most users will be launching CPython, which should have this DLL and
        // prefer to load directly, so this is helpful.
        print_error(err, L"Failed to load runtime DLL; "
                         L"attempting to launch as a new process.");
        break;
    }

    err = launch(executable, GetCommandLineW(), script, 0, (DWORD *)&exit_code);

    if (!err) {
        return exit_code;
    }

    const wchar_t *fmt = L"Failed to launch '%ls'";
    DWORD n = wcslen(fmt) + wcslen(executable) + 1;
    wchar_t *message = (wchar_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, n * sizeof(wchar_t));
    if (!message) {
        err = print_error(0, L"Failed to launch, and failed to allocate error message");
    } else {
        swprintf_s(message, n, fmt, executable);
        err = print_error(err, message);
        HeapFree(GetProcessHeap(), 0, message);
    }

    return err;
}


int WINAPI wWinMain(
    HINSTANCE hInstance,      /* handle to current instance */
    HINSTANCE hPrevInstance,  /* handle to previous instance */
    LPWSTR lpCmdLine,         /* pointer to command line */
    int nCmdShow              /* show state of window */
)
{
    return wmain(__argc, __wargv);
}
