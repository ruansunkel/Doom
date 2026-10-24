/* A small Windows API probe. It reads paths but creates no files. */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <stdio.h>
#include <string.h>

int main(void)
{
    char temp[MAX_PATH], module[MAX_PATH];
    DWORD length, version;
    LARGE_INTEGER frequency, before, after;
    ULONGLONG tick_before, tick_elapsed;
    double counter_elapsed;
    SYSTEM_INFO info;
    char *memory;

#if defined(__x86_64__)
    const char *architecture = "x86_64";
#elif defined(__i386__)
    const char *architecture = "i386";
#else
#error This probe must be compiled for i386 or x86_64.
#endif

    printf("Windows API probe: %s, %u-bit pointers\n", architecture,
           (unsigned int)(sizeof(void *) * 8));
    length = GetModuleFileNameA(NULL, module, sizeof(module));
    if (!length || length >= sizeof(module))
    {
        fprintf(stderr, "GetModuleFileNameA failed: %lu\n", GetLastError());
        return 1;
    }
    printf("Executable: %s\n", module);
    length = GetTempPathA(sizeof(temp), temp);
    if (!length || length >= sizeof(temp))
    {
        fprintf(stderr, "GetTempPathA failed: %lu\n", GetLastError());
        return 1;
    }
    printf("Windows temporary directory (read only): %s\n", temp);
    version = GetVersion();
    printf("Reported Windows version: %u.%u\n", LOBYTE(LOWORD(version)),
           HIBYTE(LOWORD(version)));
    GetSystemInfo(&info);
    if (!info.dwNumberOfProcessors || !QueryPerformanceFrequency(&frequency) ||
        frequency.QuadPart <= 0)
    {
        fprintf(stderr, "Invalid processor count or performance counter.\n");
        return 1;
    }
    printf("Processors: %lu; performance counter frequency: %lld\n",
           info.dwNumberOfProcessors, (long long)frequency.QuadPart);
    tick_before = GetTickCount64();
    if (!QueryPerformanceCounter(&before)) return 1;
    Sleep(200);
    if (!QueryPerformanceCounter(&after)) return 1;
    tick_elapsed = GetTickCount64() - tick_before;
    counter_elapsed = 1000.0 * (double)(after.QuadPart - before.QuadPart) / (double)frequency.QuadPart;
    printf("200 ms sleep: tick delta=%llu ms; performance counter delta=%.1f ms\n",
           (unsigned long long)tick_elapsed, counter_elapsed);
    if (tick_elapsed < 100 || counter_elapsed < 100.0 || counter_elapsed > 5000.0)
    {
        fprintf(stderr, "Windows clock progression is inconsistent.\n");
        return 1;
    }
    memory = HeapAlloc(GetProcessHeap(), HEAP_ZERO_MEMORY, 32);
    if (!memory)
    {
        fprintf(stderr, "HeapAlloc failed.\n");
        return 1;
    }
    strcpy(memory, "Windows heap works");
    if (strcmp(memory, "Windows heap works") || !HeapFree(GetProcessHeap(), 0, memory))
    {
        fprintf(stderr, "Windows heap verification failed.\n");
        return 1;
    }
    puts("PASS: Windows API basics.");
    return 0;
}
