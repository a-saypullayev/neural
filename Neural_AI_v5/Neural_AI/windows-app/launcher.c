/* Neural AI for Windows: a tiny native launcher that opens the site in its own app window
   (Microsoft Edge / Chrome "--app" mode: no tabs, no address bar). The site address lives in
   g_url, which the server rewrites to its own address when the file is downloaded. */
#include <windows.h>
#include <shellapi.h>
#include <stdio.h>
#include <string.h>

/* 256-byte, NUL-padded slot. The marker is replaced by the server on download. */
static volatile char g_url[256] = "@@NEURAL_URL@@";

static int exists(const char *tmpl) {
    char path[MAX_PATH];
    DWORD n = ExpandEnvironmentStringsA(tmpl, path, MAX_PATH);
    if (n == 0 || n > MAX_PATH) return 0;
    if (strchr(path, '%')) return 0; /* variable was not defined */
    return GetFileAttributesA(path) != INVALID_FILE_ATTRIBUTES;
}

static int expand(const char *tmpl, char *out) {
    DWORD n = ExpandEnvironmentStringsA(tmpl, out, MAX_PATH);
    return n > 0 && n <= MAX_PATH && !strchr(out, '%');
}

int WINAPI WinMain(HINSTANCE hi, HINSTANCE hp, LPSTR cmd, int show) {
    (void)hi; (void)hp; (void)cmd; (void)show;
    char url[256];
    memcpy(url, (const void *)g_url, sizeof url);
    url[255] = 0;
    if (strncmp(url, "http", 4) != 0) {
        MessageBoxA(NULL, "This copy of Neural AI has no website address set.\nDownload it again from your Neural AI site's /download page.",
                    "Neural AI", MB_ICONERROR);
        return 1;
    }

    static const char *browsers[] = {
        "%ProgramFiles(x86)%\\Microsoft\\Edge\\Application\\msedge.exe",
        "%ProgramFiles%\\Microsoft\\Edge\\Application\\msedge.exe",
        "%LOCALAPPDATA%\\Microsoft\\Edge\\Application\\msedge.exe",
        "%ProgramFiles%\\Google\\Chrome\\Application\\chrome.exe",
        "%ProgramFiles(x86)%\\Google\\Chrome\\Application\\chrome.exe",
        "%LOCALAPPDATA%\\Google\\Chrome\\Application\\chrome.exe",
        NULL
    };
    for (int i = 0; browsers[i]; i++) {
        if (!exists(browsers[i])) continue;
        char exe[MAX_PATH], line[MAX_PATH + 400];
        expand(browsers[i], exe);
        snprintf(line, sizeof line, "\"%s\" --app=%s", exe, url);
        STARTUPINFOA si; PROCESS_INFORMATION pi;
        ZeroMemory(&si, sizeof si); si.cb = sizeof si;
        if (CreateProcessA(NULL, line, NULL, NULL, FALSE, 0, NULL, NULL, &si, &pi)) {
            CloseHandle(pi.hThread); CloseHandle(pi.hProcess);
            return 0;
        }
    }
    /* No Edge/Chrome found: open in the default browser instead. */
    ShellExecuteA(NULL, "open", url, NULL, NULL, SW_SHOWNORMAL);
    return 0;
}
