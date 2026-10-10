// The DLLs in immediate child directories of injected_mods, and the checks the injector also runs
// before it hands one to the game.
#pragma once

#include <windows.h>

#include <string>
#include <vector>

namespace loader {

struct Mod {
  std::wstring path;
  std::wstring name;
  bool loadable = false;
  std::string why;  // rejection reason, empty when loadable
};

// *.dll files in immediate child directories of |dir|, never in |dir| itself
// or deeper descendants. Sort by file name, then full path for equal names.
std::vector<std::wstring> ListDlls(const std::wstring& dir);

// Fills in path/name, skips DLLs with a sibling <DLL filename>noinject file,
// then runs the injector's PE check (a DLL, x64).
Mod Inspect(const std::wstring& path);

// True when a module with this path is already loaded in this process. The path
// only has to name the same file, it does not have to be spelled the same way.
bool ModuleLoaded(const std::wstring& path);

// LoadLibraryW of the full path. On failure |why| carries the Win32 reason.
HMODULE Load(const std::wstring& path, std::string* why);

// Create/remove the mod-side probe flag next to a DLL before loading it.
bool SetProbeFlag(const std::wstring& dll_path, bool enabled);

}  // namespace loader
