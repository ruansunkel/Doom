/* Test Wine's HTTPS runtime using Steam's public installer metadata only. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <winhttp.h>
#include <stdio.h>

int main(void)
{
    HINTERNET session = NULL, connection = NULL, request = NULL;
    DWORD status = 0, status_size = sizeof(status);
    const char *operation = "WinHttpOpen";
    int exit_code = 1;

    puts("HTTPS probe: HEAD https://cdn.fastly.steamstatic.com/client/installer/SteamSetup.exe");
    session = WinHttpOpen(L"Independent-Wine-HTTPS-Probe/1.0",
                         WINHTTP_ACCESS_TYPE_DEFAULT_PROXY,
                         WINHTTP_NO_PROXY_NAME, WINHTTP_NO_PROXY_BYPASS, 0);
    if (!session) goto windows_error;
    operation = "WinHttpSetTimeouts";
    if (!WinHttpSetTimeouts(session, 30000, 30000, 30000, 30000)) goto windows_error;
    operation = "WinHttpConnect";
    connection = WinHttpConnect(session, L"cdn.fastly.steamstatic.com",
                                INTERNET_DEFAULT_HTTPS_PORT, 0);
    if (!connection) goto windows_error;
    operation = "WinHttpOpenRequest";
    request = WinHttpOpenRequest(connection, L"HEAD", L"/client/installer/SteamSetup.exe",
                                 NULL, WINHTTP_NO_REFERER, WINHTTP_DEFAULT_ACCEPT_TYPES,
                                 WINHTTP_FLAG_SECURE);
    if (!request) goto windows_error;
    operation = "WinHttpSendRequest";
    if (!WinHttpSendRequest(request, WINHTTP_NO_ADDITIONAL_HEADERS, 0,
                           WINHTTP_NO_REQUEST_DATA, 0, 0, 0)) goto windows_error;
    operation = "WinHttpReceiveResponse";
    if (!WinHttpReceiveResponse(request, NULL)) goto windows_error;
    operation = "WinHttpQueryHeaders";
    if (!WinHttpQueryHeaders(request, WINHTTP_QUERY_STATUS_CODE | WINHTTP_QUERY_FLAG_NUMBER,
                             WINHTTP_HEADER_NAME_BY_INDEX, &status, &status_size,
                             WINHTTP_NO_HEADER_INDEX)) goto windows_error;
    printf("HTTP status: %lu\n", status);
    if (status != 200)
    {
        fprintf(stderr, "Expected HTTP 200 from Steam's public installer endpoint.\n");
        goto cleanup;
    }
    puts("PASS: Windows WinHTTP HTTPS request; no response body downloaded.");
    exit_code = 0;
    goto cleanup;

windows_error:
    fprintf(stderr, "%s failed: Windows error %lu\n", operation, GetLastError());
cleanup:
    if (request) WinHttpCloseHandle(request);
    if (connection) WinHttpCloseHandle(connection);
    if (session) WinHttpCloseHandle(session);
    return exit_code;
}
