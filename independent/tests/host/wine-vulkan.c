/* Device creation probe only: no window, shaders, Steam, or game. */
#define VK_NO_PROTOTYPES
#ifdef _WIN32
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#else
#include <dlfcn.h>
#endif
#include <vulkan/vulkan.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int main(int argc, char **argv)
{
#ifdef _WIN32
    HMODULE library = NULL;
    char library_path[MAX_PATH];
    DWORD path_length;
#else
    void *library = NULL;
#endif
    VkInstance instance = VK_NULL_HANDLE;
    VkDevice device = VK_NULL_HANDLE;
    VkPhysicalDevice *physical_devices = NULL;
    VkExtensionProperties *extensions = NULL;
    VkQueueFamilyProperties *queues = NULL;
    uint32_t count = 0, extension_count = 0, i, j;
    const char *enabled_extension = VK_KHR_PORTABILITY_ENUMERATION_EXTENSION_NAME;
    VkResult result;
    int status = 1;
    PFN_vkGetInstanceProcAddr get_instance_proc;
    PFN_vkCreateInstance create_instance;
    PFN_vkEnumerateInstanceExtensionProperties enumerate_instance_extensions;
    PFN_vkDestroyInstance destroy_instance = NULL;
    PFN_vkEnumeratePhysicalDevices enumerate_physical_devices;
    PFN_vkGetPhysicalDeviceProperties get_properties;
    PFN_vkGetPhysicalDeviceFeatures get_features;
    PFN_vkGetPhysicalDeviceQueueFamilyProperties get_queues;
    PFN_vkEnumerateDeviceExtensionProperties enumerate_device_extensions;
    PFN_vkCreateDevice create_device;
    PFN_vkDestroyDevice destroy_device = NULL;
    VkApplicationInfo application = {0};
    VkInstanceCreateInfo instance_info = {0};

    puts("Vulkan probe: instance and graphics device creation.");
#ifdef _WIN32
    (void)argc;
    (void)argv;
    library = LoadLibraryW(L"vulkan-1.dll");
    if (!library)
    {
        fprintf(stderr, "LoadLibraryW(vulkan-1.dll) failed: %lu\n", GetLastError());
        goto cleanup;
    }
    path_length = GetModuleFileNameA(library, library_path, sizeof(library_path));
    if (!path_length || path_length >= sizeof(library_path))
    {
        fprintf(stderr, "Cannot identify the Windows Vulkan loader path.\n");
        goto cleanup;
    }
    printf("Windows Vulkan loader: %s\n", library_path);
    get_instance_proc = (PFN_vkGetInstanceProcAddr)GetProcAddress(library, "vkGetInstanceProcAddr");
#else
    if (argc != 2 || argv[1][0] != '/')
    {
        fprintf(stderr, "Usage: %s /absolute/path/to/Vulkan/library\n", argv[0]);
        goto cleanup;
    }
    printf("Native Vulkan library: %s\n", argv[1]);
    library = dlopen(argv[1], RTLD_NOW | RTLD_LOCAL);
    if (!library)
    {
        fprintf(stderr, "dlopen failed: %s\n", dlerror());
        goto cleanup;
    }
    get_instance_proc = (PFN_vkGetInstanceProcAddr)dlsym(library, "vkGetInstanceProcAddr");
#endif
    if (!get_instance_proc)
    {
        fprintf(stderr, "vkGetInstanceProcAddr is missing.\n");
        goto cleanup;
    }
    create_instance = (PFN_vkCreateInstance)get_instance_proc(VK_NULL_HANDLE, "vkCreateInstance");
    enumerate_instance_extensions = (PFN_vkEnumerateInstanceExtensionProperties)
        get_instance_proc(VK_NULL_HANDLE, "vkEnumerateInstanceExtensionProperties");
    if (!create_instance || !enumerate_instance_extensions)
    {
        fprintf(stderr, "Required global Vulkan entry points are missing.\n");
        goto cleanup;
    }
    application.sType = VK_STRUCTURE_TYPE_APPLICATION_INFO;
    application.pApplicationName = "Independent Wine Vulkan smoke probe";
    application.apiVersion = VK_API_VERSION_1_0;
    instance_info.sType = VK_STRUCTURE_TYPE_INSTANCE_CREATE_INFO;
    instance_info.pApplicationInfo = &application;
    result = enumerate_instance_extensions(NULL, &extension_count, NULL);
    if (result != VK_SUCCESS) goto vulkan_error;
    if (extension_count)
    {
        extensions = calloc(extension_count, sizeof(*extensions));
        if (!extensions) goto memory_error;
        result = enumerate_instance_extensions(NULL, &extension_count, extensions);
        if (result != VK_SUCCESS) goto vulkan_error;
        for (i = 0; i < extension_count; ++i)
        {
            if (!strcmp(extensions[i].extensionName, enabled_extension))
            {
                instance_info.flags = VK_INSTANCE_CREATE_ENUMERATE_PORTABILITY_BIT_KHR;
                instance_info.enabledExtensionCount = 1;
                instance_info.ppEnabledExtensionNames = &enabled_extension;
                break;
            }
        }
        free(extensions);
        extensions = NULL;
    }
    result = create_instance(&instance_info, NULL, &instance);
    if (result != VK_SUCCESS) goto vulkan_error;

#define LOAD_INSTANCE(variable, name) \
    variable = (PFN_##name)get_instance_proc(instance, #name); \
    if (!variable) { fprintf(stderr, "Missing %s.\n", #name); goto cleanup; }
    LOAD_INSTANCE(destroy_instance, vkDestroyInstance)
    LOAD_INSTANCE(destroy_device, vkDestroyDevice)
    LOAD_INSTANCE(enumerate_physical_devices, vkEnumeratePhysicalDevices)
    LOAD_INSTANCE(get_properties, vkGetPhysicalDeviceProperties)
    LOAD_INSTANCE(get_features, vkGetPhysicalDeviceFeatures)
    LOAD_INSTANCE(get_queues, vkGetPhysicalDeviceQueueFamilyProperties)
    LOAD_INSTANCE(enumerate_device_extensions, vkEnumerateDeviceExtensionProperties)
    LOAD_INSTANCE(create_device, vkCreateDevice)
#undef LOAD_INSTANCE

    result = enumerate_physical_devices(instance, &count, NULL);
    if (result != VK_SUCCESS) goto vulkan_error;
    if (!count)
    {
        fprintf(stderr, "No Vulkan physical devices were exposed.\n");
        goto cleanup;
    }
    physical_devices = calloc(count, sizeof(*physical_devices));
    if (!physical_devices) goto memory_error;
    result = enumerate_physical_devices(instance, &count, physical_devices);
    if (result != VK_SUCCESS) goto vulkan_error;
    for (i = 0; i < count; ++i)
    {
        VkPhysicalDeviceProperties properties;
        VkPhysicalDeviceFeatures features, enabled_features = {0};
        VkDeviceQueueCreateInfo queue_info = {0};
        VkDeviceCreateInfo device_info = {0};
        const char *portability_subset = "VK_KHR_portability_subset";
        uint32_t queue_count = 0, graphics_queue = UINT32_MAX;
        float priority = 1.0f;

        get_properties(physical_devices[i], &properties);
        get_features(physical_devices[i], &features);
        printf("GPU: %s; Vulkan %u.%u.%u; depthBounds=%u; shaderCullDistance=%u\n",
               properties.deviceName, VK_VERSION_MAJOR(properties.apiVersion),
               VK_VERSION_MINOR(properties.apiVersion), VK_VERSION_PATCH(properties.apiVersion),
               features.depthBounds, features.shaderCullDistance);
        if (!features.depthBounds || !features.shaderCullDistance) continue;
        get_queues(physical_devices[i], &queue_count, NULL);
        if (!queue_count) continue;
        queues = calloc(queue_count, sizeof(*queues));
        if (!queues) goto memory_error;
        get_queues(physical_devices[i], &queue_count, queues);
        for (j = 0; j < queue_count; ++j)
            if (queues[j].queueCount && (queues[j].queueFlags & VK_QUEUE_GRAPHICS_BIT))
            {
                graphics_queue = j;
                break;
            }
        free(queues);
        queues = NULL;
        if (graphics_queue == UINT32_MAX) continue;

        queue_info.sType = VK_STRUCTURE_TYPE_DEVICE_QUEUE_CREATE_INFO;
        queue_info.queueFamilyIndex = graphics_queue;
        queue_info.queueCount = 1;
        queue_info.pQueuePriorities = &priority;
        enabled_features.depthBounds = VK_TRUE;
        enabled_features.shaderCullDistance = VK_TRUE;
        device_info.sType = VK_STRUCTURE_TYPE_DEVICE_CREATE_INFO;
        device_info.queueCreateInfoCount = 1;
        device_info.pQueueCreateInfos = &queue_info;
        device_info.pEnabledFeatures = &enabled_features;
        extension_count = 0;
        result = enumerate_device_extensions(physical_devices[i], NULL, &extension_count, NULL);
        if (result != VK_SUCCESS) goto vulkan_error;
        if (extension_count)
        {
            extensions = calloc(extension_count, sizeof(*extensions));
            if (!extensions) goto memory_error;
            result = enumerate_device_extensions(physical_devices[i], NULL, &extension_count, extensions);
            if (result != VK_SUCCESS) goto vulkan_error;
            for (j = 0; j < extension_count; ++j)
                if (!strcmp(extensions[j].extensionName, portability_subset))
                {
                    device_info.enabledExtensionCount = 1;
                    device_info.ppEnabledExtensionNames = &portability_subset;
                    break;
                }
            free(extensions);
            extensions = NULL;
        }
        result = create_device(physical_devices[i], &device_info, NULL, &device);
        if (result != VK_SUCCESS)
        {
            fprintf(stderr, "vkCreateDevice failed for %s: %d\n", properties.deviceName, result);
            continue;
        }
        printf("PASS: graphics device created with depthBounds and shaderCullDistance (queue %u).\n",
               graphics_queue);
        puts("This does not verify presentation, DOOM rendering, or gameplay.");
        status = 0;
        goto cleanup;
    }
    fprintf(stderr, "No graphics device could enable both required DOOM features.\n");
    goto cleanup;

memory_error:
    fprintf(stderr, "Probe memory allocation failed.\n");
    goto cleanup;
vulkan_error:
    fprintf(stderr, "Vulkan operation failed: %d\n", result);
cleanup:
    free(queues);
    free(extensions);
    free(physical_devices);
    if (device && destroy_device) destroy_device(device, NULL);
    if (instance && destroy_instance) destroy_instance(instance, NULL);
    if (library)
    {
#ifdef _WIN32
        FreeLibrary(library);
#else
        dlclose(library);
#endif
    }
    return status;
}
