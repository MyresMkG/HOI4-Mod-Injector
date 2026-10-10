// Stand-in for a real injected DLL (diplo_action_hook.dll and friends):
// records in a log next to itself that its DllMain ran, and how often.
#include <windows.h>

#include <cstdio>
#include <string>

namespace {

std::wstring ModulePath(HMODULE module) {
  wchar_t buffer[MAX_PATH] = {0};
  const DWORD n = GetModuleFileNameW(module, buffer, MAX_PATH);
  return n == 0 ? std::wstring() : std::wstring(buffer, n);
}

}  // namespace

BOOL WINAPI DllMain(HINSTANCE instance, DWORD reason, LPVOID) {
  if (reason == DLL_PROCESS_ATTACH) {
    DisableThreadLibraryCalls(instance);
    const std::wstring path = ModulePath(instance);
    const size_t slash = path.find_last_of(L"\\/");
    const std::wstring dir =
        (slash == std::wstring::npos) ? std::wstring(L".") : path.substr(0, slash);
    FILE* f = _wfopen((dir + L"\\zz_test_mod.log").c_str(), L"a");
    if (f != nullptr) {
      FILETIME creation, exit, kernel, user, now;
      unsigned long long uptime = 0;
      if (GetProcessTimes(GetCurrentProcess(), &creation, &exit, &kernel, &user)) {
        GetSystemTimeAsFileTime(&now);
        const unsigned long long created =
            (static_cast<unsigned long long>(creation.dwHighDateTime) << 32) | creation.dwLowDateTime;
        const unsigned long long current =
            (static_cast<unsigned long long>(now.dwHighDateTime) << 32) | now.dwLowDateTime;
        if (current > created) uptime = (current - created) / 10000;
      }
      const DWORD flag = GetFileAttributesW((dir + L"\\diplo_action_hook_probe_only.txt").c_str());
      fprintf(f, "zz_test_mod loaded in pid %lu, uptime_ms=%llu, probe=%u\n",
              static_cast<unsigned long>(GetCurrentProcessId()), uptime,
              flag != INVALID_FILE_ATTRIBUTES && (flag & FILE_ATTRIBUTE_DIRECTORY) == 0 ? 1u : 0u);
      fclose(f);
    }
  }
  return TRUE;
}
