/* Public Steam endpoint only; never authenticate or print addresses/tokens. */
#define WIN32_LEAN_AND_MEAN
#include <winsock2.h>
#include <ws2tcpip.h>
#include <mswsock.h>
#include <windows.h>
#include <iphlpapi.h>
#include <wininet.h>
#include <stdio.h>
#include <stdlib.h>

int main(void)
{
    WSADATA data;
    ADDRINFOA hints = {0}, *addresses = NULL, *entry;
    IP_ADAPTER_ADDRESSES *adapters = NULL, *adapter;
    ULONG size = 0, adapter_result;
    unsigned int adapter_count = 0, v4_count = 0;
    DWORD internet_flags = 0, bytes = 0, transferred = 0, flags = 0;
    GUID connect_guid = WSAID_CONNECTEX;
    LPFN_CONNECTEX connect_ex = NULL;
    struct sockaddr_in local = {0};
    WSAOVERLAPPED overlapped = {0};
    SOCKET socket_handle = INVALID_SOCKET;
    int result, status = 1;
    u_long nonblocking = 1;
    fd_set writable;
    struct timeval immediate = {0};
    WSAPOLLFD poll_fd;
    HANDLE completion_port = NULL;
    OVERLAPPED completion_request = {0}, *completed = NULL;
    ULONG_PTR completion_key = 0;
    struct hostent *legacy_dns;

    if (WSAStartup(MAKEWORD(2, 2), &data)) return 1;
    printf("Windows network probe: %u-bit process.\n", (unsigned int)(8 * sizeof(void *)));
    printf("InternetGetConnectedState: %d; flags=%#lx\n",
           InternetGetConnectedState(&internet_flags, 0), internet_flags);
    adapter_result = GetAdaptersAddresses(AF_UNSPEC, 0, NULL, NULL, &size);
    if (adapter_result == ERROR_BUFFER_OVERFLOW && (adapters = malloc(size)))
    {
        adapter_result = GetAdaptersAddresses(AF_UNSPEC, 0, NULL, adapters, &size);
        if (adapter_result == NO_ERROR)
            for (adapter = adapters; adapter; adapter = adapter->Next)
            {
                IP_ADAPTER_UNICAST_ADDRESS *address;
                if (adapter->OperStatus != IfOperStatusUp) continue;
                ++adapter_count;
                for (address = adapter->FirstUnicastAddress; address; address = address->Next)
                    if (address->Address.lpSockaddr->sa_family == AF_INET) ++v4_count;
            }
    }
    printf("GetAdaptersAddresses: %lu; active=%u; IPv4 unicast=%u\n", adapter_result, adapter_count, v4_count);
    hints.ai_family = AF_INET;
    hints.ai_socktype = SOCK_STREAM;
    legacy_dns = gethostbyname("api.steampowered.com");
    printf("Steam API legacy DNS: %s; error=%d\n", legacy_dns ? "resolved" : "failed",
           legacy_dns ? 0 : WSAGetLastError());
    result = getaddrinfo("api.steampowered.com", "443", &hints, &addresses);
    printf("Steam API IPv4 DNS: %d\n", result);
    if (result || !addresses) goto cleanup;
    entry = addresses;
    socket_handle = socket(entry->ai_family, entry->ai_socktype, entry->ai_protocol);
    if (socket_handle == INVALID_SOCKET) goto socket_error;
    result = ioctlsocket(socket_handle, FIONBIO, &nonblocking);
    printf("ioctlsocket(FIONBIO): %d; error=%d\n", result, result ? WSAGetLastError() : 0);
    if (result) goto cleanup;
    result = WSAIoctl(socket_handle, SIO_GET_EXTENSION_FUNCTION_POINTER, &connect_guid, sizeof(connect_guid),
                      &connect_ex, sizeof(connect_ex), &bytes, NULL, NULL);
    printf("Get ConnectEx: %d; error=%d\n", result, result ? WSAGetLastError() : 0);
    if (result) goto cleanup;
    local.sin_family = AF_INET;
    if (bind(socket_handle, (const struct sockaddr *)&local, sizeof(local))) goto socket_error;
    overlapped.hEvent = WSACreateEvent();
    if (overlapped.hEvent == WSA_INVALID_EVENT) goto socket_error;
    if (!connect_ex(socket_handle, entry->ai_addr, (int)entry->ai_addrlen, NULL, 0, &bytes, &overlapped))
    {
        result = WSAGetLastError();
        printf("ConnectEx initial error: %d\n", result);
        if (result != WSA_IO_PENDING) goto cleanup;
        result = WSAWaitForMultipleEvents(1, &overlapped.hEvent, FALSE, 15000, FALSE);
        if (result != WSA_WAIT_EVENT_0)
        {
            fprintf(stderr, "ConnectEx wait failed/timed out: %d\n", result);
            goto cleanup;
        }
        if (!WSAGetOverlappedResult(socket_handle, &overlapped, &transferred, FALSE, &flags)) goto socket_error;
    }
    if (setsockopt(socket_handle, SOL_SOCKET, SO_UPDATE_CONNECT_CONTEXT, NULL, 0)) goto socket_error;
    FD_ZERO(&writable);
    FD_SET(socket_handle, &writable);
    result = select(0, NULL, &writable, NULL, &immediate);
    printf("select writable: %d; error=%d\n", result, result < 0 ? WSAGetLastError() : 0);
    if (result < 0) goto cleanup;
    poll_fd.fd = socket_handle;
    poll_fd.events = POLLWRNORM;
    poll_fd.revents = 0;
    result = WSAPoll(&poll_fd, 1, 0);
    printf("WSAPoll writable: %d; error=%d\n", result, result < 0 ? WSAGetLastError() : 0);
    if (result < 0) goto cleanup;
    closesocket(socket_handle);
    socket_handle = WSASocketW(AF_INET, SOCK_STREAM, IPPROTO_TCP, NULL, 0,
                              WSA_FLAG_OVERLAPPED | WSA_FLAG_NO_HANDLE_INHERIT);
    if (socket_handle == INVALID_SOCKET) goto socket_error;
    completion_port = CreateIoCompletionPort((HANDLE)socket_handle, NULL, 1234, 1);
    if (!completion_port)
    {
        fprintf(stderr, "CreateIoCompletionPort failed: %lu\n", GetLastError());
        goto cleanup;
    }
    printf("SetFileCompletionNotificationModes: %d\n",
           SetFileCompletionNotificationModes((HANDLE)socket_handle, FILE_SKIP_SET_EVENT_ON_HANDLE));
    if (bind(socket_handle, (const struct sockaddr *)&local, sizeof(local))) goto socket_error;
    if (!connect_ex(socket_handle, entry->ai_addr, (int)entry->ai_addrlen, NULL, 0, &bytes, &completion_request)
            && WSAGetLastError() != WSA_IO_PENDING) goto socket_error;
    if (!GetQueuedCompletionStatus(completion_port, &transferred, &completion_key, &completed, 15000))
    {
        fprintf(stderr, "GetQueuedCompletionStatus failed: %lu\n", GetLastError());
        goto cleanup;
    }
    if (completion_key != 1234 || completed != &completion_request) goto cleanup;
    puts("PASS: completion-port asynchronous TCP connection.");
    puts("PASS: asynchronous Winsock TCP connection to public Steam API port 443.");
    status = 0;
    goto cleanup;
socket_error:
    fprintf(stderr, "Winsock operation failed: %d\n", WSAGetLastError());
cleanup:
    if (overlapped.hEvent) WSACloseEvent(overlapped.hEvent);
    if (socket_handle != INVALID_SOCKET) closesocket(socket_handle);
    if (completion_port) CloseHandle(completion_port);
    if (addresses) freeaddrinfo(addresses);
    free(adapters);
    WSACleanup();
    return status;
}
