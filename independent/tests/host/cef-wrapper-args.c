/* Synthetic child for argument/environment/exit-status forwarding checks. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <shellapi.h>
#include <wchar.h>

int WINAPI wWinMain(HINSTANCE instance, HINSTANCE previous, WCHAR *unused, int show)
{
    static const WCHAR *expected[] = {
        L"two words", L"quote\"inside", L"trailing with space\\",
        L"--disable-gpu", L"--disable-gpu-compositing", L"--single-process"
    };
    WCHAR environment[16];
    WCHAR **arguments;
    int count, i, status = 77;
    (void)instance;
    (void)previous;
    (void)unused;
    (void)show;
    arguments = CommandLineToArgvW(GetCommandLineW(), &count);
    if (!arguments || count != 7) goto cleanup;
    for (i = 1; i < count; ++i)
        if (wcscmp(arguments[i], expected[i - 1])) goto cleanup;
    if (!GetEnvironmentVariableW(L"DOOM_WRAPPER_TEST", environment, 16) || wcscmp(environment, L"kept"))
        goto cleanup;
    status = 37;
cleanup:
    if (arguments) LocalFree(arguments);
    return status;
}
