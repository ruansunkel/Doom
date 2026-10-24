/* Launch the preserved Valve helper with CEF's Wine compatibility switches.
 * Arguments are forwarded without logging them. No credentials are handled.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <string.h>
#include <wchar.h>

static const WCHAR extra_flags[] =
    L" --disable-gpu --disable-gpu-compositing --single-process";

static const WCHAR *argument_tail(const WCHAR *command)
{
    BOOL quoted = FALSE;
    while (*command == L' ' || *command == L'\t') ++command;
    while (*command)
    {
        if (*command == L'"') quoted = !quoted;
        else if (!quoted && (*command == L' ' || *command == L'\t')) break;
        ++command;
    }
    return command;
}

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, WCHAR *unused, int show)
{
    WCHAR executable[32768], *slash, *command, *output;
    const WCHAR *tail;
    SIZE_T executable_length, tail_length, count;
    STARTUPINFOW startup = {0};
    PROCESS_INFORMATION process = {0};
    DWORD length, exit_code = 1;
    (void)instance;
    (void)previous;
    (void)unused;
    (void)show;

    length = GetModuleFileNameW(NULL, executable, 32768);
    if (!length || length >= 32768) return 1;
    slash = wcsrchr(executable, L'\\');
    if (!slash || (SIZE_T)(slash - executable + 1) + 24 >= 32768) return 1;
    wcscpy(slash + 1, L"steamwebhelper_real.exe");
    if (GetFileAttributesW(executable) == INVALID_FILE_ATTRIBUTES)
    {
        MessageBoxW(NULL, L"The preserved steamwebhelper_real.exe is missing. Reinstall the DOOM runner's Steam UI wrapper.",
                    L"DOOM runner", MB_OK | MB_ICONERROR);
        return 1;
    }
    tail = argument_tail(GetCommandLineW());
    executable_length = wcslen(executable);
    tail_length = wcslen(tail);
    count = executable_length + tail_length + wcslen(extra_flags) + 3;
    if (count > 32767) return 1;
    command = HeapAlloc(GetProcessHeap(), 0, count * sizeof(*command));
    if (!command) return 1;
    output = command;
    *output++ = L'"';
    memcpy(output, executable, executable_length * sizeof(*output));
    output += executable_length;
    *output++ = L'"';
    memcpy(output, tail, tail_length * sizeof(*output));
    output += tail_length;
    wcscpy(output, extra_flags);

    startup.cb = sizeof(startup);
    GetStartupInfoW(&startup);
    if (!CreateProcessW(executable, command, NULL, NULL, TRUE, 0, NULL, NULL, &startup, &process))
    {
        HeapFree(GetProcessHeap(), 0, command);
        MessageBoxW(NULL, L"Could not start the preserved Steam web helper.", L"DOOM runner", MB_OK | MB_ICONERROR);
        return 1;
    }
    HeapFree(GetProcessHeap(), 0, command);
    CloseHandle(process.hThread);
    if (WaitForSingleObject(process.hProcess, INFINITE) == WAIT_OBJECT_0)
        GetExitCodeProcess(process.hProcess, &exit_code);
    CloseHandle(process.hProcess);
    return (int)exit_code;
}
