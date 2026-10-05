# hoi4 1.19.3 主程序导入的 DLL 清单

分析对象：`hoi4.exe`（x64，钢铁雄心 4 1.19.3，55,778,424 字节；24 个导入模块、565 个导入函数）。
本机 Steam 版 `D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe`
与 `D:\zStudy\hoi4\hoi4_1.19.3.exe` 两份文件的导入表**逐项一致**
（24 个模块、函数个数全同），全部差异只有 **1 个字节**：

| 文件 | MD5 | 偏移 0x16E60A 处的指令 |
| --- | --- | --- |
| `D:\zStudy\hoi4\hoi4_1.19.3.exe` | `2c13d60db727e59dd21b4f27654c4a66` | `31 C0`（`xor eax,eax`） |
| Steam 版 `hoi4.exe` | `b193cb363b5024144bcf278571801fa6` | `85 C0`（`test eax,eax`） |

（该处后面紧跟 `0F 94 ??`（`sete`），是 Steam DRM 那段校验里的一个分支，两条指令对导入表无影响。）

数据来自四处，互相印证：

- **PE 导入表**：本机解析（`analysis\pe_dll_check.py`），导出表 / 延迟导入 / 绑定导入 / 清单 / TLS 一并查过；
- **本机 `\KnownDlls` 对象目录**（42 个 DLL + 1 个路径项，`analysis\known_dlls_enum.ps1`）——
  这是加载器实际使用的名单；**注册表视图只有 32 项，看不到 `bcrypt.dll`、`cfgmgr32.dll`、
  `comctl32.dll`、`crypt32.dll`、`wintrust.dll`、`kernelbase.dll`、`ntdll.dll`、`ucrtbase.dll`、
  `gdi32full.dll`、`msvcp_win.dll`、`win32u.dll`、`bcryptprimitives.dll` 这 12 个**
  （照注册表判断会得出错误结论，见下面的 `bcrypt.dll`）；
- **实机抢占测试**：把"只导出一个探针函数的假 DLL"和"按名字静态导入的 stub 程序"放同一目录
  运行，看加载器加载的是哪一份（`analysis\hijack_test\`，合并跑 + 逐名单独跑两种都做了）；
- **运行时动态加载名**：在 Ghidra dump（`hoi4_1.19.3_win_source.cpp`）里逐个 DLL 名字找
  `LoadLibrary*` / `GetModuleHandle*` 调用（`analysis\load_calls.py`），确定"谁带来、怎么加载"。

## 0. 为什么"同名文件放游戏目录就能被加载"

- 该 exe 的导入**全部是按文件名**（无完整路径、无延迟导入、无绑定导入、清单里也没有任何
  DLL 重定向——本机这个 exe 的 RT_MANIFEST 是个空 `<assembly>`）；
- Windows 默认的 DLL 搜索顺序（本机 SafeDllSearchMode 未改）：
  **exe 所在目录 → System32 → 16 位系统目录 → Windows 目录 → 当前目录 → PATH**；
- 所以：名字**不在 KnownDLLs** 里 → 游戏根目录放同名 x64 DLL 就会被优先加载；
  名字**在 KnownDLLs** 里 → 加载器直接去 System32，放什么都被忽略。

> 顺带一个和群星不一样的地方：`hoi4.exe` 自己**带一个导出表**（110 个导出 = 108 个
> `?PHYSFS_*` C++ 修饰名——PhysicsFS 整个被静态链进主程序了——外加
> `AmdPowerXpressRequestHighPerformance` / `NvOptimusEnablement` 这两个"请求独显"的常规导出）。
> 本机游戏目录里扫过的 DLL/EXE 没有一个导入它，这些导出应该是留给外部插件/工具用的。
> 写代理 DLL 时用不到，但知道它在那儿没坏处。

## 1. 主表（按导入表顺序，也就是启动时的解析顺序）

| # | 模块 | 导入函数数 | 能否被游戏目录同名 DLL 顶替 | 备注 |
| ---: | --- | ---: | --- | --- |
| 0 | `steam_api64.dll` | 16 | ✓ | 游戏自带文件（Steam 版是 Valve 原版） |
| 1 | `PDXSDK.dll` | 38 | ✓ | 游戏自带文件（1165 个 C++ 导出） |
| 2 | `SETUPAPI.dll` | 9 | ✗ 受保护 | KnownDLL |
| 3 | `IMM32.dll` | 10 | ✗ 受保护 | KnownDLL |
| 4 | `VERSION.dll` | 3 | ✓ | 本机游戏目录已被整合版占用（见附 E） |
| 5 | `WINMM.dll` | 20 | ✓ | 本机游戏目录已被整合版占用（见附 E） |
| 6 | `tbb.dll` | 22 | ✓ | **游戏自带文件**（Intel TBB，243 个导出；System32 里没有这个名字） |
| 7 | `WS2_32.dll` | 7 | ✗ 受保护 | KnownDLL；**4 个按序号导入**（`#8 htonl`、`#14 ntohl`、`#57 gethostname`、`#115 WSAStartup`） |
| 8 | `OPENGL32.dll` | 46 | ✓ | 实测 |
| 9 | `D3DCOMPILER_47.dll` | 1 | ✓ | 实测（`D3DCompile`） |
| 10 | `d3d11.dll` | 1 | ✓ | 实测（`D3D11CreateDevice`） |
| 11 | `dxgi.dll` | 2 | ✓ | 实测；**本机游戏目录已被本项目的注入器占用**（见附 E） |
| 12 | `d3dx9_43.dll` | 8 | ✓ | 实测 |
| 13 | `d3d9.dll` | 2 | ✓ | 实测（`Direct3DCreate9` / `Direct3DCreate9Ex`） |
| 14 | `XINPUT1_3.dll` | 2 | ✓ | 实测；**2 个全按序号导入**（`#2 XInputGetState`、`#4 XInputGetCapabilities`）——群星没有这个静态导入 |
| 15 | `SHLWAPI.dll` | 2 | ✗ 受保护 | KnownDLL |
| 16 | `KERNEL32.dll` | 204 | ✗ 受保护 | KnownDLL |
| 17 | `USER32.dll` | 119 | ✗ 受保护 | KnownDLL |
| 18 | `GDI32.dll` | 26 | ✗ 受保护 | KnownDLL |
| 19 | `SHELL32.dll` | 10 | ✗ 受保护 | KnownDLL |
| 20 | `ole32.dll` | 6 | ✗ 受保护 | KnownDLL |
| 21 | `OLEAUT32.dll` | 1 | ✗ 受保护 | KnownDLL；**唯一按序号导入**的（`#ord6` = `SysFreeString`） |
| 22 | `ADVAPI32.dll` | 7 | ✗ 受保护 | KnownDLL |
| 23 | `bcrypt.dll` | 3 | ✗ 受保护 | KnownDLL，但**注册表里看不到**（只有对象目录里有——照注册表判断会误判成可顶替） |

**小结**：24 个模块里，**12 个**可以被游戏目录里的同名 x64 文件顶替：

- **9 个系统 DLL**：`D3DCOMPILER_47.dll`、`d3d11.dll`、`dxgi.dll`、`d3dx9_43.dll`、
  `d3d9.dll`、`OPENGL32.dll`、`WINMM.dll`、`VERSION.dll`、`XINPUT1_3.dll`；
- **3 个游戏自带文件**：`steam_api64.dll`、`PDXSDK.dll`、`tbb.dll`
  （顶替它们等于替换游戏自己的文件，需要把原文件的导出全部转发；
  `tbb.dll` 243 个导出、`PDXSDK.dll` 1165 个、`steam_api64.dll` 966 个）。

其余 12 个名字（`SETUPAPI`、`IMM32`、`WS2_32`、`SHLWAPI`、`KERNEL32`、`USER32`、`GDI32`、
`SHELL32`、`ole32`、`OLEAUT32`、`ADVAPI32`、`bcrypt`）都在 KnownDLLs 里，
放同名文件会被忽略。

> ⚠ 本机游戏目录里 `version.dll` / `winmm.dll` 已经被整合版（Juij）的 Steam 模拟器占用、
> `dxgi.dll` 被本项目的 `hoi4_mod_injector` 占用；`steam_api64.dll` / `PDXSDK.dll` / `tbb.dll`
> 是游戏自己的文件。实际挑名字时要避开这些（详见附 E）。

## 2. 实测结果（本机 Windows 10 19045）

两种跑法都做了，结论一致：

- **合并跑**（`analysis\hijack_test\make.py`）：一个 stub exe 同时静态导入 41 个候选名，
  一次进程里看每个模块从哪儿加载 —— 结果见 `analysis\hijack_test\run\result.txt`
  （单个 exe 的导入表里同名符号只能有一个，45 个目标里有 4 个符号重名的会被链接器合并，
  这 4 个由逐名跑覆盖）；
- **逐名单独跑**（`analysis\hijack_test\make_solo.py`）：每个名字各建一个目录、各起一个只导入
  该名字的进程，避免符号重名互相干扰 —— 汇总见 `analysis\hijack_test\solo\summary.tsv`。

判定方法：假 DLL 只导出一个探针函数；stub 进程启动后 `GetModuleFileName` 指向自己目录
= APP-DIR（可顶替），指向 System32 = 受保护；若进程直接以 `0xC0000139`
（ERROR_PROC_NOT_FOUND，探针函数在系统 DLL 里不存在）起不来，同样是"受保护"的铁证。

| 结果 | 名字 |
| --- | --- |
| **从游戏目录加载成功（APP-DIR）** | `steam_api64` `PDXSDK` `tbb` `VERSION` `WINMM` `OPENGL32` `D3DCOMPILER_47` `d3d11` `dxgi` `d3dx9_43` `d3d9` `XINPUT1_3` `vulkan-1` `xinput1_4` `xinput9_1_0` `dsound` `userenv` `dbghelp` `tlhelp32` `d3dcompiler_43` `d3dcompiler_46` `wininet` `msvcp140` `vcruntime140` `vcruntime140_1` `hid` `avrt` `dinput8` `libEGL` `libGLESv2` `libGLESv1_CM` `libGLES_cm` |
| **被系统拿走（受保护）** | `SETUPAPI` `IMM32` `WS2_32` `SHLWAPI` `KERNEL32` `USER32` `GDI32` `SHELL32` `ole32` `OLEAUT32` `ADVAPI32` `bcrypt` `psapi` `shcore` `cfgmgr32` |

几条值得单独记下来的：

- 可顶替名单里，`steam_api64` / `PDXSDK` / `tbb` **在 System32 里根本不存在**
  （只能来自游戏目录）；`XINPUT1_3` 在 System32 里有（107 KB），但它还是被游戏目录的同名文件顶掉；
- `d3dcompiler_46.dll`、`libEGL.dll`、`libGLESv2.dll`、`libGLESv1_CM.dll`、`libGLES_cm.dll`
  在本机 **System32 里不存在**，放进去就是它——其中 `d3dcompiler_46/43` 是 SDL 编译着色器时的
  候选名（它按 47 → 46 → 43 顺序找），后四个是 SDL 的 GLES/EGL 驱动候选名；
- `tlhelp32.dll` 同样**不在 System32 里**（Win10 已经没有这个文件），只有你放的文件会被加载；
- `dinput8.dll` 的"成功"只说明**名字本身**可被顶替；这个 exe 里**连 `dinput8` 这个字符串都没有**
  （SDL 的 DirectInput 手柄后端在这个构建里没编进来），放进去也不会被加载。
  `libEGL` / `libGLESv2` / `libGLESv1_CM` / `libGLES_cm` 同理：除非你把 SDL 的
  `SDL_VIDEO_GL_DRIVER` / `SDL_VIDEO_EGL_DRIVER` 指过去，否则 HOI4 走
  D3D9（本机默认）/ D3D11 / OpenGL，用不到它们。

## 3. 附 A：写代理 DLL 时要转发的导出

（"谁导入它"以外，推荐把真 DLL 的全部导出都转发一遍；同一进程里别的模块也可能导入，
比如 `PDXSDK.dll` 还导入 `WININET.dll`。完整函数清单见 `analysis\exe_imports_full.txt`。）

| 名字 | 谁导入它 | 必须能提供的导出 |
| --- | --- | --- |
| `steam_api64.dll` | exe | 16 个：`SteamAPI_Init`、`SteamAPI_Shutdown`、`SteamAPI_RunCallbacks`、`SteamAPI_IsSteamRunning`、`SteamAPI_GetHSteamUser`、`SteamAPI_RegisterCallback`、`SteamAPI_UnregisterCallback`、`SteamAPI_RegisterCallResult`、`SteamAPI_UnregisterCallResult`、`SteamInternal_FindOrCreateUserInterface`、`SteamInternal_FindOrCreateGameServerInterface`、`SteamInternal_ContextInit`、`SteamInternal_GameServer_Init`、`SteamGameServer_GetHSteamUser`、`SteamGameServer_RunCallbacks`、`SteamGameServer_Shutdown` |
| `PDXSDK.dll` | exe | 38 个（C++ 修饰名，`?Set*@Config@SDK@PDX@@…` 一族；完整清单见 `exe_imports_full.txt`） |
| `tbb.dll` | exe | 22 个（C++ 修饰名：`?allocate@allocate_root_with_context_proxy@internal@tbb@@…`、`?internal_grow_by@concurrent_vector_base_v3@internal@tbb@@…` 等） |
| `VERSION.dll` | exe | `GetFileVersionInfoSizeA`、`GetFileVersionInfoA`、`VerQueryValueA` |
| `WINMM.dll` | exe | 20 个（`waveOutOpen/Write/Close/PrepareHeader/UnprepareHeader/Reset/GetNumDevs/GetDevCapsW/GetErrorTextW`、`waveIn*` 同族、`timeBeginPeriod`、`timeEndPeriod`） |
| `OPENGL32.dll` | exe | 46 个（`glReadPixels`、`glTexParameterf`、`glVertex2f` … `wglGetProcAddress`，完整清单见 `exe_imports_full.txt`） |
| `D3DCOMPILER_47.dll` | exe | `D3DCompile` |
| `d3d11.dll` | exe | `D3D11CreateDevice` |
| `dxgi.dll` | exe | `CreateDXGIFactory1`、`CreateDXGIFactory2`（另：`d3d11.dll` 也导入 `CreateDXGIFactory1`） |
| `d3dx9_43.dll` | exe | 8 个：`D3DXCreateTexture`、`D3DXCreateCubeTexture`、`D3DXCreateLine`、`D3DXCompileShader`、`D3DXLoadSurfaceFromMemory`、`D3DXLoadSurfaceFromSurface`、`D3DXSaveSurfaceToFileInMemory`、`D3DXSaveTextureToFileInMemory` |
| `d3d9.dll` | exe | `Direct3DCreate9`、`Direct3DCreate9Ex` |
| `XINPUT1_3.dll` | exe | **按序号**：`#2`= `XInputGetState`、`#4`= `XInputGetCapabilities`（SDL 运行时还会按序号 `100` 取 `XInputGetState`，见附 B） |
| ~~`WS2_32.dll`~~ | exe | `getaddrinfo`、`freeaddrinfo`、`getnameinfo` + 序号 `#8`=`htonl`、`#14`=`ntohl`、`#57`=`gethostname`、`#115`=`WSAStartup`（名字受保护，列出来仅供参考） |
| ~~`OLEAUT32.dll`~~ | exe | `#ord6` = `SysFreeString`（同上，仅供参考） |
| ~~`bcrypt.dll`~~ | exe | `BCryptGenRandom`、`BCryptOpenAlgorithmProvider`、`BCryptCloseAlgorithmProvider`（名字受保护） |

## 4. 附 B：不在导入表里、进程里同样会加载的名字

来源是主程序里的字符串 + Ghidra dump 里对应的 `LoadLibrary` 调用
（`analysis\load_calls_out.txt`、`analysis\dll_strings_ctx_out.txt`）。

| 名字 | 谁带来 / 在哪儿加载 | 实测 |
| --- | --- | --- |
| `vulkan-1.dll` | SDL（`SDL_VULKAN_LIBRARY` 提示的默认名；`hoi4_1.19.3_win_source.cpp:5639250`） | 可从游戏目录顶替 |
| `xinput1_4.dll` → `XInput1_3.dll` → `bin\XInput1_3.dll` → `xinput9_1_0.dll` | SDL 手柄驱动按这个顺序 `LoadLibraryW`（`:5715578`…），取序号 100 的函数 | 同上（四个名字都测了） |
| `dsound.dll` | SDL 音频后端（`DSOUND.DLL`，`:5640344`） | 同上 |
| `hid.dll` | SDL HIDAPI 手柄（`:5631564`）+ 另一处（`:5715516`） | 同上 |
| `avrt.dll` | SDL 音频线程优先级（`AvSetMmThreadCharacteristics`，`:5706803`） | 同上 |
| `combase.dll` | SDL 的 WinRT 手柄分支（`RoGetActivationFactory`，3 处 `LoadLibraryA`） | **受保护**（KnownDLL） |
| `comctl32.dll` | `LoadLibraryW(L"comctl32.dll")`（`:5649111`） | **受保护**（KnownDLL） |
| `cfgmgr32.dll` | `LoadLibraryA("cfgmgr32.dll")`（`:5647988`，配 SetupAPI 枚举设备） | **受保护**（KnownDLL） |
| `d3dcompiler_47.dll` → `d3dcompiler_46.dll` → `d3dcompiler_43.dll` | SDL 编译 D3D 着色器时按序尝试（`SDL_VIDEO_WIN_D3DCOMPILER`） | 均 APP-DIR（`_46`/`_43` 本机 System32 里没有） |
| `libGLESv2.dll` / `libGLESv1_CM.dll` / `libGLES_CM.dll` / `libEGL.dll` | SDL 的 GLES/EGL 驱动候选（`SDL_VIDEO_GL_DRIVER`、`SDL_VIDEO_EGL_DRIVER`） | 均 APP-DIR（名字本机 System32 里都没有） |
| `userenv.dll` | PhysicsFS（取用户目录，`:6385437`） | 可从游戏目录顶替 |
| `dbghelp.dll` | 崩溃处理器（`LoadLibraryA("dbghelp.dll")`，`:6091811`；另有一套按完整路径去 Debugging Tools 目录找的代码） | 同上 |
| `psapi.dll` | 崩溃处理器枚举模块（`LoadLibraryA/W`，`:5585272`、`:6091690`） | **受保护**（KnownDLL） |
| `tlhelp32.dll` | 崩溃处理器在 `kernel32` 拿不到 `CreateToolhelp32Snapshot` 时的回退名（`:6092142`） | APP-DIR——而且本机 System32 里没有这个文件，你放什么就是什么 |
| `wininet.dll` | `PDXSDK.dll` 的静态依赖（11 个函数） | 可从游戏目录顶替 |
| `msvcp140.dll` / `vcruntime140.dll` / `vcruntime140_1.dll` | `PDXSDK.dll`（123 / 16 / 1 个函数）与 `tbb.dll`（7 / 13 个）的静态依赖 | 同上 |
| `d3d9.dll` / `dxgi.dll` | 除了静态导入，还有运行时的 `LoadLibraryA`（`:6207335`、`:6206947`） | 同附录 A |
| `mscoree.dll` / `ntdll.dll` | 只被 `GetModuleHandleExW` / `GetModuleHandleW` **查询**（`:6462168`、`:6354446`），没有 `LoadLibrary` | 放文件也不会被加载 |

## 5. 附 C：本机 64 位 `\KnownDlls` 名单（42 个 DLL + 1 个路径项）

```
advapi32.dll   bcrypt.dll     bcryptprimitives.dll  cfgmgr32.dll  clbcatq.dll
combase.dll    comctl32.dll   comdlg32.dll          coml2.dll     crypt32.dll
difxapi.dll    gdi32.dll      gdi32full.dll         gdiplus.dll   imagehlp.dll
imm32.dll      kernel32.dll   kernelbase.dll        msctf.dll     msvcp_win.dll
msvcrt.dll     normaliz.dll   nsi.dll               ntdll.dll     ole32.dll
oleaut32.dll   psapi.dll      rpcrt4.dll            sechost.dll   setupapi.dll
shcore.dll     shell32.dll    shlwapi.dll           ucrtbase.dll  user32.dll
win32u.dll     wintrust.dll   wldap32.dll           wow64.dll     wow64cpu.dll
wow64win.dll   ws2_32.dll
（另有 KnownDllPath：路径项，不是 DLL）
```

判定方法：`analysis\known_dlls_enum.ps1`（`NtOpenDirectoryObject` + `NtQueryDirectoryObject`
枚举对象管理器里的 `\KnownDlls`）。**不要只看注册表**
`HKLM\SYSTEM\CurrentControlSet\Control\Session Manager\KnownDLLs`——注册表视图在本机只有
32 项，不含 `bcrypt.dll`、`cfgmgr32.dll`、`comctl32.dll`、`crypt32.dll`、`wintrust.dll`、
`kernelbase.dll`、`ntdll.dll`、`ucrtbase.dll`、`gdi32full.dll`、`msvcp_win.dll`、`win32u.dll`、
`bcryptprimitives.dll`，照它判断会把 `bcrypt.dll` 误判成"可顶替"
（实测它被系统抢先，进程直接 `0xC0000139` 起不来）。

## 6. 附 D：和群星 4.5 的差异（同一台机器、同一套方法）

| | 群星 4.5.1 | 钢4 1.19.3 |
| --- | --- | --- |
| 导入模块数 | 23 | **24** |
| 导入函数总数 | 658 | 565 |
| 只在钢4出现的模块 | — | **`tbb.dll`（22，Intel TBB，游戏自带）、`XINPUT1_3.dll`（2，全按序号）** |
| 只在群星出现的模块 | `nakama-sdk.dll`（1） | — |
| 两边都有但函数数不同 | 见下面的逐项对比 | 见下面的逐项对比 |
| 受保护名单 | `SETUPAPI` `KERNEL32` `USER32` `GDI32` `SHELL32` `ole32` `OLEAUT32` `ADVAPI32` `bcrypt` `WS2_32` `SHLWAPI` `IMM32`（12 个） | 完全相同的 12 个 |
| 可顶替的系统 DLL | 8 个：`D3DCOMPILER_47` `d3d11` `dxgi` `d3dx9_43` `d3d9` `OPENGL32` `WINMM` `VERSION` | 9 个：上面 8 个 + **`XINPUT1_3`** |
| 可顶替的游戏文件 | 3 个：`steam_api64` `PDXSDK` `nakama-sdk` | 3 个：`steam_api64` `PDXSDK` **`tbb`** |

两边都有、但导入函数数不同的模块（格式：群星 → 钢4）：

- `PDXSDK.dll` 146 → **38**（钢4 只用了 `Config` 那一小撮）；
- `WS2_32.dll` 31 → **7**，而且**按序号的 4 个完全一样**（`#8 htonl`、`#14 ntohl`、
  `#57 gethostname`、`#115 WSAStartup`）；
- `OPENGL32.dll` 44 → 46；`kernel32` 184 → 204；`user32` 123 → 119；`winmm` 21 → 20；
  `d3dx9_43` 7 → 8；`dxgi` 1 → 2；`gdi32` 27 → 26；`ole32` 7 → 6；`advapi32` 8 → 7；
- `OLEAUT32.dll` 两边都是 1 个，且**都是 `#ord6`**（`SysFreeString`）。

一句话：**钢4 的可顶替名单不是群星的简单加减**——少了一个 `nakama-sdk.dll`（群星联机 SDK，
钢4 里没有），多了 `tbb.dll`（Intel TBB）与 `XINPUT1_3.dll`（手柄）；受保护名单两边一模一样。

## 7. 附 F：复现用到的工具

| 文件 | 用途 |
| --- | --- |
| `analysis\pe_dll_check.py` | 解析 exe 的导入表/延迟导入/绑定导入/导出表/TLS/清单/字符串，并按 `\KnownDlls` 名单打"可否顶替"判定 |
| `analysis\exe_imports_full.txt` | 24 个模块的**完整导入函数清单**（写代理转发时照抄） |
| `analysis\exe_dll_strings.txt` | exe 里出现的所有 `*.dll` 字符串（含运行时动态加载的名字） |
| `analysis\dll_strings_ctx.py` / `dll_strings_ctx_out.txt` | 每个 DLL 名字符串所在节、编码、左右上下文、是否被引用 |
| `analysis\load_calls.py` / `load_calls_out.txt` | 在 Ghidra dump 里查每个名字的 `LoadLibrary*` / `GetModuleHandle*` 调用（判断是谁、以什么方式加载） |
| `analysis\ord_resolve.py` | 把 `#ordN` 序号导入映射回真实系统 DLL 的导出名 |
| `analysis\dll_deps.py` | 打印游戏自带 DLL（PDXSDK / tbb / steam_api64 / Juij 等）的导入导出，追依赖链 |
| `analysis\exp_grep.py` | 在某个 DLL 的导出表里按关键字过滤（例如看整合版的 `version.dll` 有没有转发 `GetFileVersionInfo*`） |
| `analysis\known_dlls_enum.ps1` / `known_dlls_actual.txt` | 枚举加载器真正使用的 `\KnownDlls` 对象目录（43 项 = 42 个 DLL + KnownDllPath） |
| `analysis\hijack_test\` | 实机抢占测试：`make.py`（合并跑）+ `make_solo.py`（逐名单独跑）+ `solo_main.cpp`；结果见 `run\result.txt`、`solo\summary.tsv`、`solo_run.log` |
| `analysis\juij_probe\` | 验证整合版 `version.dll` / `winmm.dll` 能不能当代理用的实验 |
