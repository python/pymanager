#include <windows.h>
#include <string.h>
#include <stdio.h>


static BOOL WINAPI
ctrl_c_handler(DWORD code)
{
    // just ignore control events
    return TRUE;
}


static int
dup_handle(HANDLE input, HANDLE *output)
{
    static HANDLE self = NULL;
    if (self == NULL) {
        self = GetCurrentProcess();
    }
    if (input == NULL || input == INVALID_HANDLE_VALUE) {
        *output = input;
        return 0;
    }
    if (!DuplicateHandle(self, input, self, output, 0, TRUE, DUPLICATE_SAME_ACCESS)) {
        if (GetLastError() == ERROR_INVALID_HANDLE) {
            *output = NULL;
            return 0;
        }
        return HRESULT_FROM_WIN32(GetLastError());
    }
    return 0;
}


int
launch(const wchar_t *executable, const wchar_t *insert_args, int skip_argc, DWORD *exitCode)
{
    HANDLE job;
    JOBOBJECT_EXTENDED_LIMIT_INFORMATION info;
    DWORD info_len;
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    int lastError = 0;
    const wchar_t *arg_space = L" ";
    LPCWSTR origCmdLine = GetCommandLineW();
    const wchar_t *cmdLine = NULL;

    if (insert_args == NULL) {
        insert_args = L"";
    }

    size_t n = wcslen(executable) + wcslen(origCmdLine) + wcslen(insert_args) + 5;
    wchar_t *newCmdLine = (wchar_t *)HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, n * sizeof(wchar_t));
    if (!newCmdLine) {
        lastError = GetLastError();
        goto exit;
    }

    if (origCmdLine[0] == L'"') {
        cmdLine = wcschr(origCmdLine + 1, L'"');
    } else {
        cmdLine = wcschr(origCmdLine, L' ');
    }

    while (skip_argc-- > 0) {
        wchar_t c;
        while (*++cmdLine && *cmdLine == L' ') { }
        while (*++cmdLine && *cmdLine != L' ') { }
    }

    if (!insert_args || !*insert_args) {
        arg_space = L"";
    }
    if (cmdLine && *cmdLine) {
        swprintf_s(newCmdLine, n + 1, L"\"%s\"%s%s %s", executable, arg_space, insert_args, cmdLine + 1);
    } else {
        swprintf_s(newCmdLine, n + 1, L"\"%s\"%s%s", executable, arg_space, insert_args);
    }

#if defined(_WINDOWS)
    /*
    When explorer launches a Windows (GUI) application, it displays
    the "app starting" (the "pointer + hourglass") cursor for a number
    of seconds, or until the app does something UI-ish (eg, creating a
    window, or fetching a message).  As this launcher doesn't do this
    directly, that cursor remains even after the child process does these
    things.  We avoid that by doing a simple post+get message.
    See http://bugs.python.org/issue17290
    */
    MSG msg;

    PostMessage(0, 0, 0, 0);
    GetMessage(&msg, 0, 0, 0);
#endif

    job = CreateJobObject(NULL, NULL);
    if (!job
        || !QueryInformationJobObject(job, JobObjectExtendedLimitInformation, &info, sizeof(info), &info_len)
        || info_len != sizeof(info)
    ) {
        lastError = GetLastError();
        goto exit;
    }
    info.BasicLimitInformation.LimitFlags |= JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE |
                                             JOB_OBJECT_LIMIT_SILENT_BREAKAWAY_OK;
    if (!SetInformationJobObject(job, JobObjectExtendedLimitInformation, &info, sizeof(info))) {
        lastError = GetLastError();
        goto exit;
    }

    memset(&si, 0, sizeof(si));
    GetStartupInfoW(&si);
    if ((lastError = dup_handle(GetStdHandle(STD_INPUT_HANDLE), &si.hStdInput))
        || (lastError = dup_handle(GetStdHandle(STD_OUTPUT_HANDLE), &si.hStdOutput))
        || (lastError = dup_handle(GetStdHandle(STD_ERROR_HANDLE), &si.hStdError))
    ) {
        goto exit;
    }
    if (!SetConsoleCtrlHandler(ctrl_c_handler, TRUE)) {
        lastError = GetLastError();
        goto exit;
    }

    si.dwFlags |= STARTF_USESTDHANDLES;
    if (!CreateProcessW(executable, newCmdLine, NULL, NULL, TRUE, 0, NULL, NULL, &si, &pi)) {
        lastError = GetLastError();
        goto exit;
    }

    AssignProcessToJobObject(job, pi.hProcess);
    CloseHandle(pi.hThread);
    WaitForSingleObjectEx(pi.hProcess, INFINITE, FALSE);
    if (!GetExitCodeProcess(pi.hProcess, exitCode)) {
        lastError = GetLastError();
    }
exit:
    if (newCmdLine) {
        HeapFree(GetProcessHeap(), 0, newCmdLine);
    }
    return lastError ? HRESULT_FROM_WIN32(lastError) : 0;
}
