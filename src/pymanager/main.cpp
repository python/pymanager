#include <Python.h>
#include <string.h>

#include <Windows.h>
#include <stdio.h>

#include <shellapi.h>
#include <shlobj.h>

#include <string>
#include <vector>

#include "_launch.h"
#include "src\_native\helpers.h"
#include "commands.g.h"

// HRESULT-compatible error codes
#define ERROR_NO_MATCHING_INSTALL   0xA0000004
#define ERROR_NO_INSTALLS           0xA0000005
#define ERROR_AUTO_INSTALL_DISABLED 0xA0000006

#ifndef PY_WINDOWED
#define PY_WINDOWED 0
#endif

struct {
    PyObject *mod;
    PyObject *no_install_found_error;
    PyObject *no_installs_error;
    PyObject *auto_install_disabled_error;
} manage = {NULL};


static std::wstring
get_exe_path()
{
    std::wstring path;
    while (true) {
        path.resize(path.size() + 260);
        DWORD path_len = GetModuleFileNameW(NULL, path.data(), path.size());
        if (!path_len) {
            break;
        }
        if (path_len <= path.size()) {
            path.resize(path_len);
            return path;
        }
    }
    return std::wstring();
}


static std::wstring
get_exe_directory()
{
    std::wstring path = get_exe_path();
    if (path.size()) {
        path.resize(path.find_last_of(L"/\\", path.size(), 2));
    }
    return path;
}


static std::wstring
get_root()
{
    return get_exe_directory();
}


static bool
is_env_var_set(const wchar_t *name)
{
    /* only looking for non-empty, which means at least one character
       and the null terminator */
    return GetEnvironmentVariableW(name, NULL, 0) >= 2;
}


static void
per_exe_settings(
    int argc,
    wchar_t **argv,
    const wchar_t **default_command,
    bool *commands,
    bool *cli_tag,
    bool *shebangs,
    bool *autoinstall
) {
#ifdef EXE_NAME
    const wchar_t *name = EXE_NAME;
    int cch = -1;
#else
    const wchar_t *argv0 = argv[0];
    size_t n = wcslen(argv0);
    size_t dot = 0;
    while (n > 0 && argv0[n - 1] != L'\\' && argv0[n - 1] != L'/') {
        --n;
        if (!dot && argv0[n] == L'.') {
            dot = n;
        }
    }
    int cch = dot > n ? (int)(dot - n) : -1;
    if (cch > 1 && (argv0[n + cch - 1] == L'w' || argv0[n + cch - 1] == L'W')) {
        --cch;
    }
    const wchar_t *name = &argv0[n];
#endif
    if (CompareStringOrdinal(name, cch, L"python", -1, TRUE) == CSTR_EQUAL) {
        *default_command = NULL;
        *commands = false;
        *cli_tag = false;
        *shebangs = argc >= 2;
        *autoinstall = false;
        return;
    }
    if (CompareStringOrdinal(name, cch, L"python3", -1, TRUE) == CSTR_EQUAL) {
        *default_command = NULL;
        *commands = false;
        *cli_tag = false;
        *shebangs = argc >= 2;
        *autoinstall = false;
        return;
    }
    if (CompareStringOrdinal(name, cch, L"py", -1, TRUE) == CSTR_EQUAL) {
        *default_command = NULL;
        *commands = argc >= 2;
        *cli_tag = argc >= 2;
        *shebangs = argc >= 2;
        *autoinstall = argc >= 2 && !wcscmp(argv[1], L"exec");
        return;
    }
    if (CompareStringOrdinal(name, cch, L"pymanager", -1, TRUE) == CSTR_EQUAL) {
        *default_command = argc >= 2 ? L"__help_with_error" : L"help";
        *commands = argc >= 2;
        *cli_tag = false;
        *shebangs = false;
        *autoinstall = argc >= 2 && !wcscmp(argv[1], L"exec");
        return;
    }
    // This case is for direct launches (including first run), Start menu
    // launch, or via file associations.
    *default_command = NULL;
    *commands = argc >= 2;
    *cli_tag = true;
    *shebangs = true;
    *autoinstall = true;
}


static int
read_tag_from_argv(int argc, const wchar_t **argv, int skip_argc, std::wstring &tag)
{
    if (1 + skip_argc >= argc) {
        return 0;
    }

    std::wstring arg = argv[1 + skip_argc];
    if (arg[0] != L'-' && arg[0] != L'/') {
        return 0;
    }

    if (arg.substr(1, 2) == L"V:") {
        tag = arg.substr(3);
        return 1;
    } else if (arg[1] == L'3') {
        tag = std::wstring(L"PythonCore\\") + arg.substr(1);
        return 1;
    }
    return 0;
}


static int
args_to_skip(const wchar_t *arg)
{
    int retval = 0;
    for (const wchar_t *c = arg; *c; ++c) {
        switch (*c) {
        case L'c':
        case L'm':
            return -1;
        case L'W':
        case L'X':
            retval = 1;
        case L'-':
            break;
        default:
            if (!isalnum(*c)) {
                return 0;
            }
        }
    }
    return retval;
}

static void
read_script_from_argv(int argc, const wchar_t **argv, int skip_argc, std::wstring &script)
{
    int skip = skip_argc;
    for (int i = 1; i < argc; ++i) {
        if (skip > 0) {
            --skip;
            continue;
        }
        if (argv[i][0] == L'-') {
            skip = args_to_skip(argv[i]);
            if (skip < 0) {
                break;
            }
            continue;
        }
        script = argv[i];
        return;
    }
}


static int
init_python()
{
    // Ensure we are safely loading before triggering delay loaded DLL
    if (!SetDefaultDllDirectories(LOAD_LIBRARY_SEARCH_SYSTEM32
            | LOAD_LIBRARY_SEARCH_USER_DIRS
            | LOAD_LIBRARY_SEARCH_APPLICATION_DIR)) {
        return HRESULT_FROM_WIN32(GetLastError());
    }

    std::wstring exe_dir = get_exe_directory();
    if (exe_dir.empty()) {
        return HRESULT_FROM_WIN32(GetLastError());
    }
    exe_dir += L"\\runtime";
    AddDllDirectory(exe_dir.c_str());

    PyStatus status;
    PyConfig config;
    PyConfig_InitIsolatedConfig(&config);

    config.import_time = is_env_var_set(L"PYMANAGER_IMPORT_TIME");

    status = Py_InitializeFromConfig(&config);
    if (PyStatus_Exception(status)) {
        PyConfig_Clear(&config);
        if (PyStatus_IsExit(status)) {
            return status.exitcode;
        }
        assert(PyStatus_Exception(status));
        Py_ExitStatusException(status);
        // Unreachable
        return -1;
    }

    // Ensure our main module is loadable
    manage.mod = PyImport_ImportModule("manage");
    if (!manage.mod) {
        PyErr_Print();
        return -1;
    }
    manage.no_install_found_error = PyObject_GetAttrString(manage.mod, "NoInstallFoundError");
    if (!manage.no_install_found_error) {
        PyErr_Print();
        return -1;
    }
    manage.no_installs_error = PyObject_GetAttrString(manage.mod, "NoInstallsError");
    if (!manage.no_installs_error) {
        PyErr_Print();
        return -1;
    }
    manage.auto_install_disabled_error = PyObject_GetAttrString(manage.mod, "AutomaticInstallDisabledError");
    if (!manage.auto_install_disabled_error) {
        PyErr_Print();
        return -1;
    }

    PyObject *r = PyObject_CallMethod(manage.mod, "_set_exe_name", "u", EXE_NAME);
    if (!r) {
        PyErr_Print();
        return -1;
    }
    Py_DECREF(r);

    return 0;
}


static void
close_python()
{
    assert(manage.mod);
    Py_CLEAR(manage.no_installs_error);
    Py_CLEAR(manage.no_install_found_error);
    Py_CLEAR(manage.auto_install_disabled_error);
    Py_CLEAR(manage.mod);
    Py_Finalize();
}


static int
run_command(int argc, const wchar_t **argv)
{
    int exitCode = 1;
    auto root_str = get_root();
    PyObject *args = NULL;
    PyObject *root = NULL;
    PyObject *r = NULL;

    HANDLE hGlobalSem = CreateSemaphoreExW(NULL, 0, 1,
        L"PyManager-OperationInProgress", 0, SEMAPHORE_MODIFY_STATE | SYNCHRONIZE);
    if (!hGlobalSem) {
        return GetLastError();
    } else if (GetLastError() == ERROR_ALREADY_EXISTS) {
        DWORD waitTime = 3000;
        DWORD res = WAIT_IO_COMPLETION;
        while (res == WAIT_IO_COMPLETION) {
            res = WaitForSingleObjectEx(hGlobalSem, waitTime, TRUE);
            switch (res) {
            case WAIT_OBJECT_0:
            case WAIT_ABANDONED:
                break;
            case WAIT_TIMEOUT:
                if (waitTime != INFINITE) {
                    fprintf(stderr, "Waiting for other operations to complete. . .\n");
                    waitTime = INFINITE;
                    res = WAIT_IO_COMPLETION;
                } else {
                    exitCode = WAIT_TIMEOUT;
                }
                break;
            case WAIT_FAILED:
                exitCode = GetLastError();
                break;
            default:
                res = WAIT_IO_COMPLETION;
                break;
            }
        }
    }

    args = PyList_New(0);
    if (!args) goto python_fail;
    for (int i = 0; i < argc; ++i) {
        PyObject *s = PyUnicode_FromWideChar(argv[i], -1);
        if (!s) goto python_fail;
        if (PyList_Append(args, s) < 0) {
            Py_DECREF(s);
            goto python_fail;
        }
        Py_DECREF(s);
    }
    root = PyUnicode_FromWideChar(root_str.c_str(), -1);
    if (!root) goto python_fail;
    r = PyObject_CallMethod(manage.mod, "main", "OO", args, root);
    if (r) {
        exitCode = PyLong_AsLong(r);
        goto done;
    }
python_fail:
    PyErr_Print();
done:
    ReleaseSemaphore(hGlobalSem, 1, NULL);
    CloseHandle(hGlobalSem);
    Py_XDECREF(r);
    Py_XDECREF(root);
    Py_XDECREF(args);
    return exitCode;
}


static int
run_simple_command(const wchar_t *argv0, const wchar_t *cmd)
{
    int exitCode = 1;
    auto root_str = get_root();
    PyObject *args = NULL;
    PyObject *root = NULL;
    PyObject *r = NULL;

    args = Py_BuildValue("(uu)", argv0, cmd);
    if (!args) goto python_fail;
    root = PyUnicode_FromWideChar(root_str.c_str(), -1);
    if (!root) goto python_fail;
    r = PyObject_CallMethod(manage.mod, "main", "OO", args, root);
    if (r) {
        exitCode = PyLong_AsLong(r);
        goto done;
    }
python_fail:
    PyErr_Print();
done:
    Py_XDECREF(r);
    Py_XDECREF(root);
    Py_XDECREF(args);
    return exitCode;
}


static int
auto_install_runtime(
    const wchar_t *argv0,
    const std::wstring &tag,
    const std::wstring &script,
    int err_cause
)
{
    int err = 0;
    const wchar_t *new_argv[] = { argv0, NULL, NULL, NULL, NULL };

    new_argv[1] = L"install";
    new_argv[2] = L"--automatic";
    if (!tag.empty()) {
        new_argv[3] = tag.c_str();
        err = run_command(4, new_argv);
    } else if (!script.empty()) {
        new_argv[3] = L"--from-script";
        new_argv[4] = script.c_str();
        err = run_command(5, new_argv);
    } else {
        err = run_command(3, new_argv);
    }
    return err;
}


static int
locate_runtime(
    const std::wstring &tag,
    const std::wstring &script,
    std::wstring &executable,
    std::wstring &args,
    int autoinstall_permitted,
    int print_not_found_error
) {
    int exitCode = 1;
    auto root_str = get_root();
    PyObject *r = NULL;

    r = PyObject_CallMethod(manage.mod, "find_one", "uuuiii",
        root_str.c_str(), tag.c_str(), script.c_str(), PY_WINDOWED, autoinstall_permitted, print_not_found_error);
    if (!r) {
        if (PyErr_ExceptionMatches(manage.no_installs_error)) {
            exitCode = ERROR_NO_INSTALLS;
        } else if (PyErr_ExceptionMatches(manage.no_install_found_error)) {
            exitCode = ERROR_NO_MATCHING_INSTALL;
        } else if (PyErr_ExceptionMatches(manage.auto_install_disabled_error)) {
            exitCode = ERROR_AUTO_INSTALL_DISABLED;
        }
        // Other errors should already have been printed
        PyErr_Clear();
        goto done;
    } else {
        wchar_t *w_exe, *w_args;
        if (!PyArg_ParseTuple(r, "O&O&", as_utf16, &w_exe, as_utf16, &w_args)) {
            PyErr_Print();
            goto done;
        }
        executable = w_exe;
        args = w_args;
        PyMem_Free(w_exe);
        PyMem_Free(w_args);
        exitCode = 0;
    }
done:
    Py_XDECREF(r);
    return exitCode;
}


int
wmain(int argc, wchar_t **argv)
{
    int err = 0;
    DWORD exitCode;
    std::wstring executable, args, tag, script;
    int skip_argc = 0;

    err = init_python();
    if (err) {
        return err;
    }

    CoInitializeEx(NULL, COINIT_APARTMENTTHREADED);

    const wchar_t *default_cmd;
    bool use_commands, use_cli_tag, use_shebangs, use_autoinstall;
    per_exe_settings(argc, argv, &default_cmd, &use_commands, &use_cli_tag, &use_shebangs, &use_autoinstall);

    if (use_commands) {
        // Subcommands list is generated at sdist/build time and stored
        // in commands.g.h
        for (const wchar_t **cmd_name = subcommands; *cmd_name; ++cmd_name) {
            if (!wcscmp(argv[1], *cmd_name)) {
                err = run_command(argc, (const wchar_t **)argv);
                goto error;
            }
        }

        // We handle 'exec' in native code, so it won't be in the above list
        if (!wcscmp(argv[1], L"exec")) {
            skip_argc += 1;
            use_cli_tag = argc >= 3;
            use_shebangs = argc >= 3;
            default_cmd = NULL;
        }
    }

    // Use the default command if we have one
    if (default_cmd) {
        if (!wcscmp(default_cmd, L"__help_with_error")) {
            const wchar_t *new_argv[] = {argv[0], default_cmd, argv[1]};
            return run_command(3, new_argv);
        }
        return run_simple_command(argv[0], default_cmd);
    }

    if (use_cli_tag && read_tag_from_argv(argc, (const wchar_t **)argv, skip_argc, tag)) {
        skip_argc += 1;
        use_shebangs = false;
    }

    if (use_shebangs) {
        read_script_from_argv(argc, (const wchar_t **)argv, skip_argc, script);
    }

    err = locate_runtime(tag, script, executable, args, use_autoinstall ? 1 : 0, 0);

    if (err == ERROR_NO_MATCHING_INSTALL || err == ERROR_NO_INSTALLS) {
        err = auto_install_runtime(argv[0], tag, script, err);
        if (!err) {
            err = locate_runtime(tag, script, executable, args, 1, 1);
        }
    }

    if (err == ERROR_NO_MATCHING_INSTALL
        || err == ERROR_NO_INSTALLS
        || err == ERROR_AUTO_INSTALL_DISABLED
    ) {
        // Error has already been displayed
        goto error;
    }

    if (err) {
        // Most 'not found' errors have been handled above. These are internal
        fprintf(stderr, "[ERROR] Internal error 0x%08X. "
                "Please report to https://github.com/python/pymanager\n", err);
        goto error;
    }

    // Theoretically shouldn't matter, but might help reduce memory usage.
    close_python();

    err = launch(executable.c_str(), args.c_str(), skip_argc, &exitCode);

    // TODO: Consider sharing print_error() with launcher.cpp
    // This will ensure error messages are aligned whether we're launching
    // through py.exe or through an alias.
    switch (err) {
    case 0:
        err = (int)exitCode;
        break;
    case ERROR_EXE_MACHINE_TYPE_MISMATCH:
    case HRESULT_FROM_WIN32(ERROR_EXE_MACHINE_TYPE_MISMATCH):
        fprintf(stderr,
                "[ERROR] Executable '%ls' is for a different kind of "
                "processor architecture.\n",
                executable.c_str());
        fprintf(stderr,
                "Try using '-V:<version>' to select a different runtime, or use "
                "'py install' to install one for your CPU.\n");
        break;
    default:
        fprintf(stderr, "[ERROR] Failed to launch '%ls' (0x%08X)\n", executable.c_str(), err);
        fprintf(stderr, "This may be a corrupt install or a system configuration issue.\n");
        break;
    }
    return err;

error:
    close_python();
    return err;
}


#if PY_WINDOWED

int WINAPI
wWinMain(HINSTANCE hInstance, HINSTANCE hPrevInstance, LPWSTR lpCmdLine, int nCmdShow)
{
    return wmain(__argc, __wargv);
}

#endif
