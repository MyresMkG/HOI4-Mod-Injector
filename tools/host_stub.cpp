// Stand-in for hoi4.exe used by tools/run_tests.py.
//
// It imports the same functions the game imports from all nine proxy names --
// the list was taken from hoi4.exe 1.19.3 (the file in the game folder,
// md5 2c13d60db727e59dd21b4f27654c4a66) -- so a forwarder that cannot be
// resolved fails loudly at load time instead of silently. A few of them are
// called for real (version size, the winmm timer, the D3D9/DXGI/D3D11
// factories, D3DCompile, D3DXCompileShader, glGetString/glGetError, XInput),
// the module paths are printed so the test can see which ones came from the
// test folder, and then it stays alive for a few seconds so the loader thread
// inside the proxy has time to load injected_mods.
//
// The game's import lists, for reference (85 functions over the nine names):
//   VERSION.dll        GetFileVersionInfoA, GetFileVersionInfoSizeA, VerQueryValueA
//   WINMM.dll          timeBeginPeriod, timeEndPeriod, waveIn* (10), waveOut* (9)
//   d3d11.dll          D3D11CreateDevice
//   dxgi.dll           CreateDXGIFactory1, CreateDXGIFactory2
//   d3d9.dll           Direct3DCreate9, Direct3DCreate9Ex
//   OPENGL32.dll       44 gl* calls plus wglGetProcAddress and wglGetCurrentDC
//   D3DCOMPILER_47.dll D3DCompile
//   d3dx9_43.dll       D3DXCreateTexture, D3DXCreateCubeTexture, D3DXCreateLine,
//                      D3DXLoadSurfaceFromMemory, D3DXLoadSurfaceFromSurface,
//                      D3DXCompileShader, D3DXSaveTextureToFileInMemory,
//                      D3DXSaveSurfaceToFileInMemory
//   XINPUT1_3.dll      ordinal 2 (XInputGetState) and 4 (XInputGetCapabilities).
//                      The game imports these two *by ordinal*; the stub has to
//                      link them by name (no toolchain here writes an ordinal
//                      import), so it looks the two ordinals up at run time and
//                      compares them against the named functions -- and a miss
//                      fails the host, the way it would fail the game.

#define WINVER 0x0A00
#define _WIN32_WINNT 0x0A00

#include <windows.h>
#include <d3d9.h>
#include <d3d11.h>
#include <d3dcompiler.h>
#include <d3dx9.h>
#include <dxgi.h>
#include <dxgi1_3.h>
#include <mmsystem.h>
#include <winver.h>
#include <xinput.h>

#include <GL/gl.h>

#include <cstdio>
#include <cstring>

namespace {

const char* kNames[] = {"dxgi.dll",  "d3d11.dll",         "d3d9.dll",        "version.dll",
                        "winmm.dll", "opengl32.dll",     "d3dcompiler_47.dll",
                        "d3dx9_43.dll", "xinput1_3.dll"};

// Spelled out instead of __uuidof so the test does not depend on compiler
// extensions; a wrong IID would only turn the result into E_NOINTERFACE.
const GUID kIID_IDXGIFactory1 = {0x770aae78, 0xf26f, 0x4dba,
                                 {0xa8, 0x29, 0x25, 0x3c, 0x83, 0xd1, 0xb3, 0x87}};
const GUID kIID_IDXGIFactory2 = {0x50c83a1c, 0xe072, 0x4c48,
                                 {0x87, 0xb0, 0x36, 0x30, 0xfa, 0x36, 0xa6, 0xd0}};

DWORD WINAPI IdleThread(void*) { return 0; }

// The imports that are only here so the loader has to resolve them: reading
// their addresses at run time is enough to force the entries into the import
// table (a mere array that nobody reads would be optimised away). Calling them
// would open devices the test does not need.
volatile unsigned long long g_refs_seen = 0;
const void* const kResolveOnlyRefs[] = {
    // WINMM.dll -- the game's full wave in/out list.
    reinterpret_cast<const void*>(&waveInAddBuffer),
    reinterpret_cast<const void*>(&waveInClose),
    reinterpret_cast<const void*>(&waveInGetDevCapsW),
    reinterpret_cast<const void*>(&waveInGetNumDevs),
    reinterpret_cast<const void*>(&waveInOpen),
    reinterpret_cast<const void*>(&waveInPrepareHeader),
    reinterpret_cast<const void*>(&waveInReset),
    reinterpret_cast<const void*>(&waveInStart),
    reinterpret_cast<const void*>(&waveInUnprepareHeader),
    reinterpret_cast<const void*>(&waveOutClose),
    reinterpret_cast<const void*>(&waveOutGetDevCapsW),
    reinterpret_cast<const void*>(&waveOutGetErrorTextW),
    reinterpret_cast<const void*>(&waveOutOpen),
    reinterpret_cast<const void*>(&waveOutPrepareHeader),
    reinterpret_cast<const void*>(&waveOutReset),
    reinterpret_cast<const void*>(&waveOutUnprepareHeader),
    reinterpret_cast<const void*>(&waveOutWrite),
    // VERSION.dll and d3d9.dll -- called below; referenced here as well so the
    // list above is the complete one the game has.
    reinterpret_cast<const void*>(&GetFileVersionInfoA),
    reinterpret_cast<const void*>(&VerQueryValueA),
    reinterpret_cast<const void*>(&Direct3DCreate9Ex),
    // OPENGL32.dll -- the engine's GL 1.1 set. Opening a GL context needs a
    // window and a pixel format, which the test does not have; the addresses
    // alone are what makes the loader resolve all 46 forwards.
    reinterpret_cast<const void*>(&glVertex2f),
    reinterpret_cast<const void*>(&glTexSubImage2D),
    reinterpret_cast<const void*>(&glTexParameteri),
    reinterpret_cast<const void*>(&glTexParameterf),
    reinterpret_cast<const void*>(&glTexImage2D),
    reinterpret_cast<const void*>(&glTexEnvf),
    reinterpret_cast<const void*>(&glStencilOp),
    reinterpret_cast<const void*>(&glStencilMask),
    reinterpret_cast<const void*>(&glStencilFunc),
    reinterpret_cast<const void*>(&glScissor),
    reinterpret_cast<const void*>(&glReadPixels),
    reinterpret_cast<const void*>(&glPolygonMode),
    reinterpret_cast<const void*>(&glPixelStorei),
    reinterpret_cast<const void*>(&glOrtho),
    reinterpret_cast<const void*>(&glMatrixMode),
    reinterpret_cast<const void*>(&glLoadIdentity),
    reinterpret_cast<const void*>(&glLineWidth),
    reinterpret_cast<const void*>(&glViewport),
    reinterpret_cast<const void*>(&glGetString),
    reinterpret_cast<const void*>(&glGetIntegerv),
    reinterpret_cast<const void*>(&glGetFloatv),
    reinterpret_cast<const void*>(&glGetError),
    reinterpret_cast<const void*>(&glAlphaFunc),
    reinterpret_cast<const void*>(&glGetBooleanv),
    reinterpret_cast<const void*>(&glGenTextures),
    reinterpret_cast<const void*>(&glFrontFace),
    reinterpret_cast<const void*>(&wglGetCurrentDC),
    reinterpret_cast<const void*>(&glEnd),
    reinterpret_cast<const void*>(&glEnable),
    reinterpret_cast<const void*>(&glDrawElements),
    reinterpret_cast<const void*>(&glDrawArrays),
    reinterpret_cast<const void*>(&glDisable),
    reinterpret_cast<const void*>(&glDepthMask),
    reinterpret_cast<const void*>(&glBegin),
    reinterpret_cast<const void*>(&glBindTexture),
    reinterpret_cast<const void*>(&glBlendFunc),
    reinterpret_cast<const void*>(&wglGetProcAddress),
    reinterpret_cast<const void*>(&glGetTexImage),
    reinterpret_cast<const void*>(&glClear),
    reinterpret_cast<const void*>(&glClearColor),
    reinterpret_cast<const void*>(&glColor4f),
    reinterpret_cast<const void*>(&glColorMask),
    reinterpret_cast<const void*>(&glCopyTexSubImage2D),
    reinterpret_cast<const void*>(&glCullFace),
    reinterpret_cast<const void*>(&glDeleteTextures),
    reinterpret_cast<const void*>(&glDepthFunc),
    // d3dx9_43.dll -- D3DXCompileShader is called below; the rest need a D3D9
    // device or a texture the test has no use for.
    reinterpret_cast<const void*>(&D3DXCreateTexture),
    reinterpret_cast<const void*>(&D3DXCreateCubeTexture),
    reinterpret_cast<const void*>(&D3DXCreateLine),
    reinterpret_cast<const void*>(&D3DXLoadSurfaceFromMemory),
    reinterpret_cast<const void*>(&D3DXLoadSurfaceFromSurface),
    reinterpret_cast<const void*>(&D3DXSaveTextureToFileInMemory),
    reinterpret_cast<const void*>(&D3DXSaveSurfaceToFileInMemory),
};

}  // namespace

int main(int argc, char** argv) {
  // --no-pump: like the launcher's start, where the proxy is walked on a thread
  // of its own and the game's own message loop only starts much later. Nothing
  // pumps here; the only wake-up left for the proxy is a thread appearing.
  const bool no_pump = argc > 1 && strcmp(argv[1], "--no-pump") == 0;

  char exe[MAX_PATH] = {0};
  GetModuleFileNameA(nullptr, exe, MAX_PATH);
  printf("host    : %s%s\n", exe, no_pump ? " (no message loop)" : "");

  unsigned refs = 0;
  for (const void* p : kResolveOnlyRefs) {
    g_refs_seen ^= reinterpret_cast<unsigned long long>(p);
    ++refs;
  }
  printf("refs    : %u resolve-only import(s), sink 0x%llx\n", refs, g_refs_seen);

  for (const char* name : kNames) {
    HMODULE module = GetModuleHandleA(name);
    char path[MAX_PATH] = {0};
    if (module == nullptr) {
      printf("%-12s: NOT LOADED\n", name);
      continue;
    }
    GetModuleFileNameA(module, path, MAX_PATH);
    printf("%-12s: %s\n", name, path);
  }

  DWORD handle = 0;
  const DWORD size = GetFileVersionInfoSizeA("C:/Windows/System32/ntdll.dll", &handle);
  printf("version size : %lu\n", static_cast<unsigned long>(size));

  const MMRESULT timer_hr = timeBeginPeriod(1);
  printf("timeBeginPeriod : %u\n", static_cast<unsigned>(timer_hr));
  if (timer_hr == TIMERR_NOERROR) timeEndPeriod(1);
  printf("wave devices : %u\n", static_cast<unsigned>(waveOutGetNumDevs()));

  IDirect3D9* d3d9 = Direct3DCreate9(D3D_SDK_VERSION);
  printf("d3d9 factory : %p\n", reinterpret_cast<void*>(d3d9));
  if (d3d9 != nullptr) d3d9->Release();

  IDirect3D9Ex* d3d9ex = nullptr;
  const HRESULT d3d9ex_hr = Direct3DCreate9Ex(D3D_SDK_VERSION, &d3d9ex);
  printf("d3d9ex factory : hr=0x%08lx ptr=%p\n", static_cast<unsigned long>(d3d9ex_hr),
         reinterpret_cast<void*>(d3d9ex));
  if (d3d9ex != nullptr) d3d9ex->Release();

  IDXGIFactory1* factory = nullptr;
  const HRESULT dxgi_hr = CreateDXGIFactory1(kIID_IDXGIFactory1,
                                             reinterpret_cast<void**>(&factory));
  printf("dxgi factory : hr=0x%08lx ptr=%p\n", static_cast<unsigned long>(dxgi_hr),
         reinterpret_cast<void*>(factory));
  if (factory != nullptr) factory->Release();

  IDXGIFactory2* factory2 = nullptr;
  const HRESULT dxgi2_hr = CreateDXGIFactory2(0, kIID_IDXGIFactory2,
                                              reinterpret_cast<void**>(&factory2));
  printf("dxgi factory2 : hr=0x%08lx ptr=%p\n", static_cast<unsigned long>(dxgi2_hr),
         reinterpret_cast<void*>(factory2));
  if (factory2 != nullptr) factory2->Release();

  ID3D11Device* device = nullptr;
  ID3D11DeviceContext* context = nullptr;
  D3D_FEATURE_LEVEL level = D3D_FEATURE_LEVEL_9_1;
  const HRESULT d3d11_hr = D3D11CreateDevice(nullptr, D3D_DRIVER_TYPE_HARDWARE, nullptr, 0,
                                             nullptr, 0, D3D11_SDK_VERSION, &device, &level,
                                             &context);
  printf("d3d11 device : hr=0x%08lx level=0x%04x\n", static_cast<unsigned long>(d3d11_hr),
         static_cast<unsigned>(level));
  if (context != nullptr) context->Release();
  if (device != nullptr) device->Release();

  // The four names that came after the original five: the two shader compilers,
  // the GL entry points the engine imports, and the pad. All of them answer
  // without a game: a shader compiles, GL reports its state even with no
  // context current (glGetString is NULL then), and a missing pad is a normal
  // return value. What matters for the test is that the call is reached at all:
  // a forwarder that did not resolve fails the load, and one that landed on the
  // wrong function is what these results would show.
  static const char kHlsl[] = "float4 main() : SV_Position { return float4(0, 0, 0, 1); }";
  ID3DBlob* shader = nullptr;
  ID3DBlob* shader_errors = nullptr;
  const HRESULT compile_hr = D3DCompile(kHlsl, sizeof(kHlsl) - 1, "host_stub", nullptr,
                                        nullptr, "main", "vs_4_0", 0, 0, &shader,
                                        &shader_errors);
  printf("D3DCompile : hr=0x%08lx bytecode=%lu\n", static_cast<unsigned long>(compile_hr),
         static_cast<unsigned long>(shader != nullptr ? shader->GetBufferSize() : 0));
  const bool compile_ok = compile_hr == S_OK && shader != nullptr;
  if (shader_errors != nullptr) shader_errors->Release();
  if (shader != nullptr) shader->Release();

  static const char kD3dxHlsl[] = "float4 main() : POSITION { return 0; }";
  ID3DXBuffer* d3dx_code = nullptr;
  ID3DXBuffer* d3dx_errors = nullptr;
  ID3DXConstantTable* d3dx_table = nullptr;
  const HRESULT d3dx_hr = D3DXCompileShader(kD3dxHlsl, sizeof(kD3dxHlsl) - 1, nullptr,
                                            nullptr, "main", "vs_1_1", 0, &d3dx_code,
                                            &d3dx_errors, &d3dx_table);
  printf("D3DXCompileShader : hr=0x%08lx bytecode=%lu\n", static_cast<unsigned long>(d3dx_hr),
         static_cast<unsigned long>(d3dx_code != nullptr ? d3dx_code->GetBufferSize() : 0));
  const bool d3dx_ok = d3dx_hr == S_OK && d3dx_code != nullptr;
  if (d3dx_table != nullptr) d3dx_table->Release();
  if (d3dx_errors != nullptr) d3dx_errors->Release();
  if (d3dx_code != nullptr) d3dx_code->Release();

  const GLubyte* gl_version = glGetString(GL_VERSION);
  printf("glGetString : %s\n",
         gl_version != nullptr ? reinterpret_cast<const char*>(gl_version)
                               : "(no GL context, as expected here)");
  printf("glGetError : %u, wglGetCurrentDC : %p\n", static_cast<unsigned>(glGetError()),
         reinterpret_cast<void*>(wglGetCurrentDC()));

  XINPUT_STATE pad_state;
  ZeroMemory(&pad_state, sizeof(pad_state));
  const DWORD pad_hr = XInputGetState(0, &pad_state);
  XINPUT_CAPABILITIES pad_caps;
  ZeroMemory(&pad_caps, sizeof(pad_caps));
  const DWORD pad_caps_hr = XInputGetCapabilities(0, 0, &pad_caps);
  printf("XInputGetState : %lu, XInputGetCapabilities : %lu (1167 = no pad is fine)\n",
         static_cast<unsigned long>(pad_hr), static_cast<unsigned long>(pad_caps_hr));

  // The game takes these two out of XINPUT1_3.dll *by ordinal* (2 and 4), which
  // is something no toolchain here can write into this stub's import table
  // (dlltool does not take "module.#ordinal" either). So the stub asks the
  // loaded module the same question the loader asks it: the ordinal has to be
  // there, and it has to land on the same function the name lands on. A proxy
  // that lost the ordinals, or moved them, fails here instead of in the game --
  // and in the game that failure is the process refusing to start.
  HMODULE xinput = GetModuleHandleA("xinput1_3.dll");
  const FARPROC xinput_ord2 =
      xinput != nullptr ? GetProcAddress(xinput, (LPCSTR)MAKEINTRESOURCEA(2)) : nullptr;
  const FARPROC xinput_ord4 =
      xinput != nullptr ? GetProcAddress(xinput, (LPCSTR)MAKEINTRESOURCEA(4)) : nullptr;
  const FARPROC xinput_name2 =
      xinput != nullptr ? GetProcAddress(xinput, "XInputGetState") : nullptr;
  const FARPROC xinput_name4 =
      xinput != nullptr ? GetProcAddress(xinput, "XInputGetCapabilities") : nullptr;
  const bool xinput_ordinals = xinput_ord2 != nullptr && xinput_ord4 != nullptr &&
                               xinput_ord2 == xinput_name2 && xinput_ord4 == xinput_name4;
  printf("xinput ord2/4 : %p/%p, by name %p/%p -> %s\n",
         reinterpret_cast<void*>(xinput_ord2), reinterpret_cast<void*>(xinput_ord4),
         reinterpret_cast<void*>(xinput_name2), reinterpret_cast<void*>(xinput_name4),
         xinput_ordinals ? "both land on the same functions" : "MISMATCH");

  const bool calls_ok = size != 0 && timer_hr == TIMERR_NOERROR && compile_ok && d3dx_ok &&
                        xinput_ordinals;

  // The proxy loader 1.1 does not start its thread at attach any more: it waits
  // for a thread attach or for the host's first message loop, so the stub does
  // what a game does -- it starts a worker and then pumps messages for a few
  // seconds -- and stays alive long enough for the mods to be loaded.
  if (no_pump) {
    // The launcher's shape: nobody pumps, and the first thread after start-up
    // arrives late. That thread attach is the only wake-up the proxy can use.
    Sleep(1200);
    HANDLE late = CreateThread(nullptr, 0, IdleThread, nullptr, 0, nullptr);
    if (late != nullptr) {
      WaitForSingleObject(late, 2000);
      CloseHandle(late);
    }
    Sleep(2500);
    printf("host done\n");
    fflush(stdout);
    return calls_ok ? 0 : 1;
  }

  // A game pumps its message loop and starts threads, and so does the stub -- in
  // the order that keeps the wake-up honest: the proxy's timer only fires while
  // this thread is inside a message loop, so the loop is entered first and the
  // thread is started two seconds later. The other order leaves it to a race
  // between that thread's attach and the timer, and a thread attach is the path
  // t8_nopump covers on purpose (it is what the launcher start takes in the
  // game).
  MSG msg;
  const DWORD until = GetTickCount() + 4000;
  bool worker_started = false;
  while (GetTickCount() < until) {
    while (PeekMessageW(&msg, nullptr, 0, 0, PM_REMOVE)) {
      TranslateMessage(&msg);
      DispatchMessageW(&msg);
    }
    if (!worker_started && GetTickCount() + 2000 >= until) {
      HANDLE worker = CreateThread(nullptr, 0, IdleThread, nullptr, 0, nullptr);
      if (worker != nullptr) {
        WaitForSingleObject(worker, 2000);
        CloseHandle(worker);
      }
      worker_started = true;
    }
    Sleep(1);
  }

  printf("host done\n");
  fflush(stdout);
  return calls_ok ? 0 : 1;
}
