#include "config.h"

#include <windows.h>

#include "log.h"
#include "util.h"

namespace loader {
namespace {

const char kDefaultIni[] =
    "; HOI4 Mod Injector configuration (read on each game start).\r\n"
    "; delay_ms: minimum process age before loading DLLs, in milliseconds.\r\n"
    "; The game's CRT must still be ready, even with delay_ms=0.\r\n"
    "; probe: 0 = normal loading, 1 = resolve addresses without hooking.\r\n"
    "; Probe mode requires mod support for diplo_action_hook_probe_only.txt.\r\n"
    "; probe=0 removes that flag beside each loadable DLL before loading.\r\n"
    "[injector]\r\n"
    "delay_ms=700\r\n"
    "probe=0\r\n";

bool ParseDelay(const wchar_t* text, unsigned long* value) {
  if (*text == L'\0') return false;
  unsigned long long parsed = 0;
  for (; *text != L'\0'; ++text) {
    if (*text < L'0' || *text > L'9') return false;
    parsed = parsed * 10 + (*text - L'0');
    // INFINITE is reserved by Sleep; reject it and stop before overflow.
    if (parsed >= INFINITE) return false;
  }
  *value = static_cast<unsigned long>(parsed);
  return true;
}

}  // namespace

Config ReadConfig(const std::wstring& path) {
  Config config;
  // Several proxy DLLs can start together. Readers must wait until the first
  // proxy finishes writing the default configuration.
  wchar_t mutex_name[80];
  swprintf(mutex_name, 80, L"Local\\hoi4_mod_injector_config_%lu",
           static_cast<unsigned long>(GetCurrentProcessId()));
  HANDLE mutex = CreateMutexW(nullptr, FALSE, mutex_name);
  bool holding = false;
  if (mutex != nullptr) {
    const DWORD waited = WaitForSingleObject(mutex, INFINITE);
    holding = waited == WAIT_OBJECT_0 || waited == WAIT_ABANDONED;
  }

  HANDLE file = CreateFileW(path.c_str(), GENERIC_WRITE, FILE_SHARE_READ, nullptr,
                            CREATE_NEW, FILE_ATTRIBUTE_NORMAL, nullptr);
  if (file != INVALID_HANDLE_VALUE) {
    DWORD written = 0;
    const DWORD length = static_cast<DWORD>(sizeof(kDefaultIni) - 1);
    const bool ok = WriteFile(file, kDefaultIni, length, &written, nullptr) && written == length;
    CloseHandle(file);
    Log(ok ? "ini   : created default %s" : "warning: could not write default %s",
        Narrow(path).c_str());
  } else {
    const DWORD error = GetLastError();
    if (error != ERROR_FILE_EXISTS && error != ERROR_ALREADY_EXISTS) {
      Log("warning: could not create %s: %s; reading available settings or defaults",
          Narrow(path).c_str(), ErrorText(error).c_str());
    }
  }

  wchar_t value[64];
  const DWORD length = GetPrivateProfileStringW(L"injector", L"delay_ms", L"700",
                                                 value, 64, path.c_str());
  if (length == 63 || !ParseDelay(value, &config.delay_ms)) {
    Log("warning: invalid delay_ms; using 700");
  }
  GetPrivateProfileStringW(L"injector", L"probe", L"0", value, 64, path.c_str());
  if (wcscmp(value, L"1") == 0) {
    config.probe = true;
  } else if (wcscmp(value, L"0") != 0) {
    Log("warning: invalid probe; using 0");
  }
  Log("ini   : %s, delay_ms=%lu, probe=%u", Narrow(path).c_str(), config.delay_ms,
      config.probe ? 1u : 0u);
  if (mutex != nullptr) {
    if (holding) ReleaseMutex(mutex);
    CloseHandle(mutex);
  }
  return config;
}

}  // namespace loader
