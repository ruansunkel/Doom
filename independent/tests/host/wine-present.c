/* Clear/present only: no shaders, browser, Steam, or game. */
#define COBJMACROS
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <d3d11.h>
#include <stdio.h>

static IDXGISwapChain *swapchain;
static ID3D11DeviceContext *context;
static ID3D11RenderTargetView *target;
static unsigned int presented;
static int presentation_failed;

static LRESULT CALLBACK window_proc(HWND window, UINT message, WPARAM wparam, LPARAM lparam)
{
    if (message == WM_TIMER)
    {
        const float green[4] = {0.05f, 0.85f, 0.2f, 1.0f};
        HRESULT result;
        ID3D11DeviceContext_ClearRenderTargetView(context, target, green);
        result = IDXGISwapChain_Present(swapchain, 1, 0);
        if (FAILED(result))
        {
            presentation_failed = 1;
            fprintf(stderr, "Present failed: %#lx\n", (unsigned long)result);
            DestroyWindow(window);
        }
        else if (++presented == 1)
        {
            puts("First Direct3D frame presented. The window should be bright green.");
            fflush(stdout);
        }
        return 0;
    }
    if (message == WM_DESTROY)
    {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcA(window, message, wparam, lparam);
}

int main(void)
{
    WNDCLASSA window_class = {0};
    DXGI_SWAP_CHAIN_DESC desc = {0};
    ID3D11Device *device = NULL;
    ID3D11Texture2D *buffer = NULL;
    D3D_FEATURE_LEVEL level;
    const D3D_FEATURE_LEVEL levels[] = {D3D_FEATURE_LEVEL_11_0, D3D_FEATURE_LEVEL_10_0};
    HWND window;
    MSG message;
    HRESULT result;
    int status = 1;

    window_class.lpfnWndProc = window_proc;
    window_class.hInstance = GetModuleHandleA(NULL);
    window_class.lpszClassName = "DoomRunnerPresentProbe";
    if (!RegisterClassA(&window_class)) return 1;
    window = CreateWindowA(window_class.lpszClassName, "DOOM runner display test - should be GREEN",
            WS_OVERLAPPEDWINDOW, CW_USEDEFAULT, CW_USEDEFAULT, 640, 360,
            NULL, NULL, window_class.hInstance, NULL);
    if (!window) return 1;
    desc.BufferDesc.Format = DXGI_FORMAT_R8G8B8A8_UNORM;
    desc.SampleDesc.Count = 1;
    desc.BufferUsage = DXGI_USAGE_RENDER_TARGET_OUTPUT;
    desc.BufferCount = 2;
    desc.OutputWindow = window;
    desc.Windowed = TRUE;
    desc.SwapEffect = DXGI_SWAP_EFFECT_DISCARD;
    result = D3D11CreateDeviceAndSwapChain(NULL, D3D_DRIVER_TYPE_HARDWARE, NULL, 0,
            levels, 2, D3D11_SDK_VERSION, &desc, &swapchain, &device, &level, &context);
    if (FAILED(result)) goto cleanup;
    result = IDXGISwapChain_GetBuffer(swapchain, 0, &IID_ID3D11Texture2D, (void **)&buffer);
    if (FAILED(result)) goto cleanup;
    result = ID3D11Device_CreateRenderTargetView(device, (ID3D11Resource *)buffer, NULL, &target);
    if (FAILED(result)) goto cleanup;
    printf("Direct3D device created with feature level %#x. Close the test window when finished.\n", level);
    ShowWindow(window, SW_SHOWNORMAL);
    SetTimer(window, 1, 16, NULL);
    while (GetMessageA(&message, NULL, 0, 0) > 0)
    {
        TranslateMessage(&message);
        DispatchMessageA(&message);
    }
    if (presented && !presentation_failed) status = 0;
cleanup:
    if (FAILED(result)) fprintf(stderr, "Direct3D setup failed: %#lx\n", (unsigned long)result);
    if (target) ID3D11RenderTargetView_Release(target);
    if (buffer) ID3D11Texture2D_Release(buffer);
    if (context) ID3D11DeviceContext_Release(context);
    if (device) ID3D11Device_Release(device);
    if (swapchain) IDXGISwapChain_Release(swapchain);
    if (IsWindow(window)) DestroyWindow(window);
    return status;
}
