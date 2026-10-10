#pragma once

#include <string>

namespace loader {

struct Config {
  unsigned long delay_ms = 700;
  bool probe = false;
};

// Create a commented default INI only when absent, then read [injector].
// Invalid or missing values use defaults; existing files are never rewritten.
Config ReadConfig(const std::wstring& path);

}  // namespace loader
