# HOI4-Mod-Injector

`hoi4_mod_injector` 的**代理 DLL 版**源码 —— 就是 `stellaris_mod_injector_dll`
在 HOI4 上的对应物：把"启动游戏后注入 injected_mods"
搬进游戏进程内部 —— 靠顶替一个游戏启动时一定会加载的系统 DLL（`dxgi.dll` / `winmm.dll` /
`version.dll` / `d3d11.dll` / `d3d9.dll` / `opengl32.dll` / `d3dcompiler_47.dll` /
`d3dx9_43.dll` / `xinput1_3.dll`，一共九种），加载器就在游戏进程里跑，不需要外部工具。

源码从 `stellaris` 项目的 `stellaris_mod_injector_dll_src` 移植而来，
宿主进程名改为 `hoi4.exe`，项目名改为 `hoi4_mod_injector`。
2026-10-10 更新：日志改为游戏根目录下的
`injected_mods\hoi4_mod_injector.log`；DLL 只扫描
`injected_mods\<一级子目录>\*.dll`，不扫描 `injected_mods` 本层或更深目录。
各一级子目录里的 DLL 合并后按文件名排序（不区分大小写），同名时按完整路径排序。
互斥量、PE 检查和日志头中的内部名 `hoi4_mod_loader 1.1 -- proxy '...'` 保留原有约定。
配置统一放在 `injected_mods\hoi4_mod_injector.ini`，不存在时自动生成带注释的默认配置，
已有文件不覆盖。旧版 `hoi4_mod_loader.ini` 和 `hoi4_mod_loader_probe.txt` 不再读取。

```ini
[injector]
delay_ms=700
probe=0
```

`delay_ms` 是加载 DLL 前的最小进程年龄（毫秒，从进程创建时算起），默认 700。
接受 0–4294967294 的十进制整数；缺少参数或值无效时使用默认值，无效值会写日志。
设为 0 也不绕过 CRT 初始化和安全唤醒检查。`probe` 只接受 0 或 1，默认 0；
1 表示只探测，0 表示正常加载。修改配置后重启游戏生效。

成品和面向玩家的说明在 `..\..\full_releases\hoi4_mod_injector\`。

---

## 1. 目录

```
hoi4_mod_injector_src/
├── build.bat                     一键编译九种（默认全编，`build.bat <名字...>` 只编指定的），
│                                 产物写到 ..\..\full_releases\hoi4_mod_injector\
├── README.md                     本文件
├── src/
│   ├── dllmain.cpp               DllMain（只登记 + 查标志位）+ 延迟启动 + 加载流程
│   ├── crtprobe.h / crtprobe.cpp 在主 exe 里找"游戏 CRT 是否已经初始化"的标志位
│   ├── config.h / config.cpp     默认 INI 生成、delay_ms 与 probe 读取及校验
│   ├── mods.h / mods.cpp         injected_mods 扫描、PE 检查、加载、probe 标记
│   ├── log.h / log.cpp           覆盖式日志（每次启动重写）+ OutputDebugString
│   └── util.h / util.cpp         路径、UTF-8、Win32 错误文本
├── def/                          每种名字的导出清单（生成物，别手改，见第 4 节）
│   ├── dxgi.def  d3d11.def  d3d9.def  version.def  winmm.def
│   └── opengl32.def  d3dcompiler_47.def  d3dx9_43.def  xinput1_3.def
└── tools/
    ├── gen_proxy_def.py          从本机 System32 生成 def\<name>.def（含按序号转发没有名字的导出）
    ├── run_tests.py              编译 + 全部自动检查（导出表、宿主桩、加载流程、负例）
    ├── host_stub.cpp             测试宿主：导入 hoi4.exe 实际导入的那 85 个函数，起一条线程并跑消息循环
    ├── test_mod.cpp              测试 mod：记录自己的 DllMain 跑了几次
    ├── check_game_imports.py     拿真实 hoi4.exe 核对宿主桩的导入表（第 5.3 节）
    ├── check_crt_probe.cpp       拿一个真实的游戏 exe 验证 crtprobe 还能找到标志位
    └── suspended_start_check.cpp 复现启动器的启动方式（进程挂起 + 由别的线程走导入表）
├── build/                        测试用的小工具编译产物（可删）
├── build_out/                    测试编译的产物（run_tests.py 生成，可删）
└── test_out/                     测试宿主与各用例目录（同上，可删）
```

## 2. 工作原理

1. **冒充**：每种构建都链接 `def/<name>.def`。这个 def 里列着同名系统 DLL 的**全部
   命名导出和它们的原始序号**，每个都是转发器（forwarder），指向
   `C:/Windows/System32/<name>.<Func>`。所以进程里任何模块从 `dxgi.dll` 等名字上
   拿到的东西和真文件一一对应，连序号都对得上（`tools/run_tests.py` 会逐个核对）。
   转发用正斜杠是因为 GNU ld 的 .def 词法把 `\` 当转义（反斜杠写法会编译失败）。
2. **DllMain**：只记句柄、查一次标志位、登记一个回调定时器，然后立刻返回。
   它在 loader lock 里、而且是在游戏自己的导入还没解析完的时候被调用，
   所以这里不能建线程（1.1 起也不再建，原因见下），也不能干别的。
3. **延迟启动（1.1）**：`src/crtprobe.cpp` 在主 exe 里找那个"-1 表示还没分配"的
   TLS 索引变量 —— 它的值是 `-1` 时，游戏自己的 CRT 还处在启动过程中，
   这时候任何新线程都会被游戏的 TLS 回调送进 `abort()`（0xC0000409 / BEX64）。
   所以线程只在两处创建：
   - `DllMain(DLL_THREAD_ATTACH)`：游戏自己起了一条新线程，且标志位说 CRT 好了；
   - 回调定时器：加载线程进入消息循环（游戏自己的主循环），且标志位说 CRT 好了。

   两条路都晚于游戏自己的启动。真要是都等不到（30 秒），就在当时那条**已经初始化**
   的线程上直接加载（`start : the CRT stayed unready for ...`）——建线程才危险，
   在已有线程上跑不危险。找不到标志位（别的宿主、别的 CRT）时退回按时间等
   （`kNoProbeSafeMs` = 700 ms）那一套。
4. 线程起来之后：确认宿主是 `hoi4.exe` → 生成或读取 INI → 等进程满
   `delay_ms`（默认 700 ms，起点是进程创建时刻）→ 取一个按 pid 命名的互斥量
   （玩家装多个名字时只有一个负责加载，
   其余会看到 "was already loaded in the process"）→ 只扫
   `injected_mods\<一级子目录>\*.dll`（不扫本层，不递归），
   合并后按**文件名顺序**（同名按完整路径，均不区分大小写）→ 检查同目录的
   `<DLL文件名>noinject` 文件，有则跳过 → 与注入器**同一套**
   PE 检查（是 DLL、x64），坏文件跳过并写明原因 → `LoadLibraryW` 全路径逐个加载，
   每个都写一行 `ok (module ...)` 或 `FAILED: ...` → 汇总 `N of M DLL(s) loaded`。
   日志写在**游戏根目录下的 `injected_mods\hoi4_mod_injector.log`**。
   `injected_mods` 不存在时先创建目录，并在日志中提示建立子目录放 DLL。
   **每次启动覆盖**，文件里只有这一次
   运行：玩家看的永远是刚才那次，昨天的失败不会再混进来。各个 mod 自己的日志
   仍写在它们自己的子目录里（那些是追加的）。旧版的 `hoi4_mod_loader.log`
   不会自动迁移或删除，新版不再写入这个文件名。
5. INI 的 `[injector] probe=1` 时，在每个可加载 DLL 旁边生成
   `diplo_action_hook_probe_only.txt`（= 注入器的 `--probe`）；只有支持该标记的 mod
   才会只解析地址而不安装钩子。`probe=0` 时，在加载 DLL 前删除对应的标记，
   包括旧版遗留的标记。创建或删除失败会写警告。只同步本次扫描到的可加载 DLL
   旁边的标记，不处理本层或更深目录。旧的 `hoi4_mod_loader_probe.txt` 不再生效。

### 禁用单个 DLL（dllnoinject）

从 `stellaris_mod_injector_dll_src` 引入同样的禁用规则：在
`injected_mods\my_mod\hook.dll` 旁创建空文件 `hook.dllnoinject`。
文件内容不限，名称是在完整 DLL 文件名后直接追加 `noinject`；
`hook.noinject`、`hook.dllnoload` 和名为 `hook.dllnoinject` 的目录都不会禁用 DLL。
标记只影响同目录的对应 DLL，其他子目录的同名 DLL 照常处理。

检查在打开 DLL、PE 校验和探测标记处理之前完成。禁用 DLL 仍计入候选数量，
不计入待加载数量，日志会写 `[skip] hook.dll: disabled by hook.dllnoinject`。
禁用期间不会创建或清除该 DLL 对应的探测标记；同目录还有其他可加载 DLL 时，
它们仍按配置处理共享的探测标记。删除禁用文件后，下次启动恢复正常加载和探测处理。
此规则只控制本加载器，不卸载已加载的 DLL，也不能阻止其他模块自行加载它。

### 为什么 DllMain 里不再创建线程（1.1）

1.0 在 DllMain 里立刻 `CreateThread`。当游戏是**直接**启动时，主线程几乎总能先跑到
CRT 初始化，所以看不出来；但**从启动器启动**时不是这样：Paradox Launcher 拉起的
进程被创建成挂起状态，`gameoverlayrenderer64.dll`（Steam 覆盖层）挂进去的线程
替游戏走完导入表 —— 我们那条线程这时也被创建了，而游戏的主线程还没被恢复，
CRT 初始化根本没机会跑。于是我们线程的 TLS 回调先执行，发现 CRT 的索引还是 `-1`，
按 CRT 自己的规矩 `abort()`。这条链是在**移植源**（Stellaris 4.5.1，同一台机器）上
核出来的：两份崩溃转储里出错线程的起始地址都是 `dxgi.dll+0x14b0`（加载器线程函数），
这是定位的决定性证据。HOI4 用的是同一族的 MSVC CRT（代理照常等它），
标志位本身已在本机 `hoi4.exe` 1.19.3 上核对（见第 5.3 节）。

`tools/suspended_start_check.cpp` 就是把这条启动方式复现成一个工具：进程挂起、
在它里面起一条线程（让导入表在那条线程上走完），然后看进程还在不在。
1.0 的产物在这个工具下于主线程被恢复之前就死了，1.1 的产物活着。
（工具恢复主线程之后的访问违例不算数：那一步**没有任何代理**时也会发生，
是"导入表由别的线程走完、那条线程又走了"这件事本身带来的，工具的注释里写了。）

### 为什么没有"等加载器空闲"的探测

`LoadLibraryW` 自己会阻塞在 loader lock 上：如果游戏镜像还没初始化完，加载会自然推迟到
初始化结束，不需要（也不应该）额外探测。这不是理论 —— 试过并测出问题
（在移植源的 Stellaris 上测的，结论照搬，代码没改）：

本机实验（Windows 10 19045，宿主 = 只导入 dxgi 的最小 exe，命名为游戏 exe 名，
代理用真的 def，只换 DllMain 的行为）：

| 变体 | 结果 |
| --- | --- |
| 纯转发，DllMain 不起线程 | 正常 |
| DllMain 起线程，只写日志 | 直接启动正常；**挂起启动崩溃**（见上） |
| 上面 + `LdrLockLoaderLock(TRY_ONLY)` 轮询探测 | **卡死**：宿主停在 `CreateDXGIFactory1`，探测一直报"锁忙" |
| 上面改为延迟后 `LoadLibraryW`（不探测） | 正常 |

也就是说，从"进程初始化期间创建的线程"里去 TRY_ONLY 探测加载器锁，会把加载器锁搞成
永远拿不到的状态。所以最终版**只保留 delay + 让 LoadLibrary 自己阻塞 + 等 CRT 标志位**，
并在 `src/dllmain.cpp`、`src/crtprobe.h` 里写明了原因。

## 3. 编译

```
build.bat                          默认把九个名字都编一遍
build.bat opengl32 d3dx9_43        也可以只编指定的那几个
```

需要 MinGW-w64 的 `g++` 在 PATH 里，或设置 `MINGW_BIN`。产物（九种 DLL）写到
`..\..\full_releases\hoi4_mod_injector\`。全部静态链接：产物的导入表只有 `KERNEL32.dll`
和 UCRT 的 api-ms 集（`ucrtbase.dll`，Windows 10 自带），不依赖 MinGW 运行库。

设 `OUTDIR` 可以编译到别处（`tools\run_tests.py` 就是这么做的，所以跑测试不会
覆盖已经实机验证过的产物）：

```
set OUTDIR=D:\tmp\proxy && build.bat
```

## 4. 重新生成导出清单

System32 里的这些 DLL 换了版本（或系统目录不是 `C:\Windows`）时：

```
py -3 tools\gen_proxy_def.py                  默认重新生成九个
py -3 tools\gen_proxy_def.py opengl32 dxgi    也可以只生成其中几个
```

它读每个系统 DLL 的导出表，写出 `def\<name>.def`（名字 + 原序号 + 转发目标）。

**只有序号、没有名字**的导出用 `"<系统路径>.#<序号>" @ <序号> NONAME` 转发（三个
部分都不能少）：加载器认这种转发器写法，所以按序号导入的调用方照样能用 —— 游戏从
`xinput1_3.dll` 导入的两个函数就正是按序号（2 和 4）走的。引号也是必须的：GNU ld
的 .def 词法把 `#` 当行注释，不引起来那一行就是语法错误，而 `NONAME` 让它在这里
也保持"没有名字"，跟真文件一个形状（`tools/run_tests.py` 会逐个核对）。

本机 System32 里没有名字的导出：`d3d9.dll` 6 个（序号 16-19、22、23）、`winmm.dll`
1 个（序号 2）、`xinput1_3.dll` 4 个（序号 100-103，即那几个不在头文件里的
`XInput*Ex`）。

## 5. 测试

```
py -3 tools\run_tests.py            （编译到 build_out\，再跑全部检查）
py -3 tools\run_tests.py --no-build （只跑检查，用 build_out\ 里现成的产物）
py -3 tools\run_tests.py --out ..\..\full_releases\hoi4_mod_injector --no-build
                                    （检查已经发布的那些 DLL）
```

测试自己编译到 `build_out\`，`build.bat` 的产物（`..\..\full_releases\hoi4_mod_injector\`）
不会被碰；两边都存在时会比对 `.text` 段，并注明"发布的 DLL 就是刚测过的这份代码"
还是"和刚测的这份不是同一份代码"。

391 项自动检查，全部离线（不碰游戏）：

1. **导出表核对**（每种名字）：名字集合一致、无多余名字、序号一致、每个导出都转发回
   System32 的真文件；**只有序号、没有名字**的导出同样逐个核对（在不在、序号对不对、
   转发目标是不是那个序号）；
2. **宿主桩**：一个导入了"游戏实际导入的那些函数"（九种名字一共 85 个）的 exe，真调用
   `GetFileVersionInfoSizeA`（必须拿到真实大小）、`timeBeginPeriod`、`Direct3DCreate9` /
   `Direct3DCreate9Ex`、`CreateDXGIFactory1` / `CreateDXGIFactory2`、`D3D11CreateDevice`、
   `D3DCompile` 与 `D3DXCompileShader`（真编一段 HLSL，必须拿到字节码）、`glGetString` /
   `glGetError`，并调用 `XInputGetState` / `XInputGetCapabilities`、再按**序号 2/4**
   取一次那两个函数、要求和同名导入落到同一个地址（游戏正是按序号导入的）；
   转发器解析不了的话它在启动阶段就会失败；
3. **加载流程**（九种名字各一遍）：测试 mod 被加载且 DllMain 只跑一次、32 位 DLL / 非 PE
   文件 / MZ 合法但头偏移坏掉的文件被跳过并写明原因、子目录里叫 `*.dll` 的**目录**
   不算候选、loader 自己那份副本被跳过、日志与汇总行正确，
   且日志写在 `injected_mods\hoi4_mod_injector.log`，不生成根目录日志或旧名称日志；
   在本层和更深目录放入有效 DLL，确认它们既不成为候选也不加载；
   多个一级子目录（含名字以 `.dll` 结尾的目录）和大写 `.DLL` 扩展名均能加载，
   并按全局文件名顺序加载；
   另外每种名字都要求 `start :` 行说加载线程是**被消息循环叫醒**的（而不是在挂接时
   就创建）、无 CRT 探测的测试宿主叫醒时刻不早于 700 ms；
   默认 INI 自动生成且包含注释，日志记录实际使用的 `delay_ms` 和 `probe`；
4. **负例**：宿主不是 `hoi4.exe` 时拒绝加载、缺 `injected_mods` 时创建日志目录并写指引、
   三个代理同时装时只加载一遍、INI 探测开关在 DLL 的 DllMain 执行前正确生成或清除标记；
5. **启动器那种启动方式**：宿主不跑消息循环、只在 1.2 秒后起一条线程 —— 这时
   只有 `DLL_THREAD_ATTACH` 能叫醒代理，要求日志写出
   `start : a thread attached after the CRT was up` 且 mod 照常加载；
6. **配置**：自定义 1800 ms 和 0 ms 延迟，核对 DLL 实际加载的进程年龄；已有 INI
   逐字节保持不变；负数、非数字、溢出和过长值回退默认；缺参数用默认；旧探测文件无效。
7. **禁用单个 DLL**（九种代理各一遍）：空标记与非空标记均生效，禁用优先于 PE
   检查；标记文件不成为候选；目录和错误后缀不生效；其他目录同名 DLL 不受影响；
   禁用 DLL 不加载且不处理探测标记；删除禁用文件后，下次启动恢复加载。

### 游戏相关的三个工具（不进自动测试）

游戏需要真实文件，这三件事没法离线做，各配了一个小工具（都在 `tools\` 下，都可以单独编译）：

- `check_crt_probe.cpp` —— 拿一个真实的游戏 exe，验证 `src/crtprobe.cpp` 还能找到
  那个 CRT 标志位（`found at rva 0x...`；找不到不影响使用，只是退回按时间等的路径）。
  用法：

  ```
  g++ -std=c++17 -O2 -o check_crt_probe.exe tools\check_crt_probe.cpp src\crtprobe.cpp
  check_crt_probe.exe "D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe"
  ```

- `check_game_imports.py` —— 拿真实游戏 exe 核对 `tools\host_stub.cpp` 的导入表：
  桩存在的意义就是"游戏从这九个名字上导入的每一个函数，桩都要导入"，游戏更新后
  导入表可能变，跑一遍就知道桩还对不对（`xinput1_3.dll` 那两个**序号**导入没法写进
  桩的导入表 —— 没有工具链支持 —— 所以桩改成运行时按序号取一次来核对）：

  ```
  py -3 tools\check_game_imports.py "D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe"
  ```

- `suspended_start_check.cpp` —— 复现启动器的启动方式（进程挂起，导入表由另一条线程
  走完），看代理会不会在那之前就创建线程而把游戏弄死。判定看
  `process still alive after N s` 这一行；工具里也写明了恢复主线程之后的访问违例
  与代理无关（没有任何代理时同样发生）。用法：

  ```
  g++ -std=c++17 -O2 -o suspended_start_check.exe tools\suspended_start_check.cpp
  suspended_start_check.exe "D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe" 8
  ```

### 本次构建验证（2026-10-10）

`py -3 tools\run_tests.py`：391 项检查，0 失败。
九种代理 DLL 全部重新编译，测试通过后从 `build_out\` 更新到
`..\..\full_releases\hoi4_mod_injector\`，逐个核对 SHA256 与已测试的 DLL 相同。
完整记录见成品目录的 `验证日志_离线自动测试_20261010_DLLNOINJECT.txt`。
先前 INI 配置构建的记录保留在 `验证日志_离线自动测试_20261010_INI.txt`。
先前仅调整日志路径与扫描层级的构建记录保留在 `验证日志_离线自动测试_20261010.txt`。
本次未重新运行真实游戏；下方实机记录对应更新前的构建与目录布局。

### 历史本机结果（Windows 10 19045，2026-10-05）

- `hoi4.exe` 1.19.3（游戏目录里那份，md5 `b193cb363b5024144bcf278571801fa6`；见上面
  "实机验证"里的说明，这份是 2026-10-03 被改过的，工作目录里另存了一份 9 月 17 日的
  `2c13d60db727e59dd21b4f27654c4a66`）：
  - `check_crt_probe`：`found at rva 0x30c7820, ready=0` —— 标志位形状与移植源
    （Stellaris 4.5.1 的 `0x2805b50`）同族，代理走"等 CRT"这条路，不走 700 ms 兜底；
  - `check_game_imports.py`：桩覆盖了游戏从九个名字导入的全部 85 个函数
    （VERSION 3 / WINMM 20 / d3d11 1 / dxgi 2 / d3d9 2 / OPENGL32 46 /
    D3DCOMPILER_47 1 / d3dx9_43 8 / XINPUT1_3 2 个**序号**导入），一个不缺；
  - 全部 216 项离线检查通过，两次：一次测刚编出来的产物、一次直接测发布目录里那九个
    DLL（原始输出见成品目录的 `验证日志_离线自动测试.txt`）。

### 历史实机验证（更新前的目录布局）

真游戏 1.19.3（游戏目录 `D:\SteamLibrary\steamapps\common\Hearts of Iron IV`，
`injected_mods` 里一个测试 mod `zz_test_mod.dll`，记录自己的 DllMain 跑了几次）。

下面除 `d3d9.dll` 与"挂起启动"两条是 2026-09-30 的旧记录（那一版还有 ini 功能，
游戏目录里的 `hoi4.exe` 也还是 md5 `2c13d60db727e59dd21b4f27654c4a66` 那份）以外，
其余都是 2026-10-05 拿**现编现测的那九个 DLL**重跑出来的；那天游戏目录里的 `hoi4.exe`
是 10 月 3 日被改过的那一份（同尺寸，md5 `b193cb363b5024144bcf278571801fa6`；
CRT 标志位仍是 `hoi4.exe+0x30c7820`、导入表一个不少 —— `check_crt_probe` 与
`check_game_imports.py` 都按这个文件重跑过）。工作目录里的 `hoi4_1.19.3.exe` 仍是
9 月 17 日那份 `2c13d60d...`。

- **`dxgi.dll` 代理，直接启动**：代理在 688 ms 内加载完 mod（`waiting 442 ms before
  loading` 那行说明它还在等固定的 700 ms），
  `crt : per-thread data flag at hoi4.exe+0x30c7820, ready`、
  `start : a thread attached after the CRT was up (257 ms into the process)`，
  游戏正常到主菜单（窗口标题 `Hearts of Iron IV (DirectX 9)`，Responding=True），
  测试 mod 的日志写着它在该游戏进程里跑了一次。原始日志：
  `..\..\full_releases\hoi4_mod_injector\验证日志_实机_dxgi代理.log`；
- **`d3d9.dll` 代理，直接启动**（2026-09-30 的旧记录）：代理在 641 ms 内加载完 mod。
  本机这个版本就是走 DX9 渲染，也就是说渲染路径真的从代理的转发器上过了一遍；
  原始日志：`验证日志_实机_d3d9代理.log`；
- **`opengl32.dll` / `d3dcompiler_47.dll` / `d3dx9_43.dll` / `xinput1_3.dll` 四个新名字
  各装一次，直接启动**（2026-10-05，四个名字都用现编的那份）：四个都各自把 mod 加载完
  （609–703 ms），窗口到 `Hearts of Iron IV (DirectX 9)` 且应答（150–154 s）。
  `xinput1_3.dll` 这一次尤其说明问题：游戏是从它身上**按序号**（2/4）导入的，
  代理连序号一起转发，所以游戏带着它照样启动。原始日志：
  `验证日志_实机_opengl32代理.log`、`验证日志_实机_d3dcompiler_47代理.log`、
  `验证日志_实机_d3dx9_43代理.log`、`验证日志_实机_xinput1_3代理.log`；
- **五个一起装**（`dxgi` + 上面四个，2026-10-05）：一份日志里五段都在，先到的那个加载
  mod（610 ms）、其余四个写 `ok (was already loaded in the process)`（日志是共用一份，
  行会交错），游戏照常到主菜单并应答（153 s）。原始日志：`验证日志_实机_五代理同装.log`；
- **启动器那种启动方式**：`suspended_start_check.exe` 把游戏挂起、由另一条线程走完导入表 ——
  主线程被恢复之前进程一直活着（`process still alive after 8 s`，没有早建线程的那种
  `0xC0000409`），恢复之后游戏照常到主菜单；代理到第 20053 ms 才被线程挂接叫醒
  （`start : a thread attached after the CRT was up (20053 ms into the process)`）并加载 mod。
  原始记录：`验证日志_实机_挂起启动.log`。

### 没有验证的部分

- `version.dll` / `winmm.dll` 没有在 HOI4 上实机装载过：这两个名字在本机游戏目录里被
  整合版的 Steam 模拟器（Juij）占着，装上去会顶掉它，所以只做了离线验证
  （导出表 + 宿主桩 + 加载流程）；
- `d3d11.dll` 也只在离线测试里装过（本机游戏默认走 DX9，没有为它单独实机跑一遍）；
- 新加的那四个名字每个都单独实机跑过一次、也一起装过一次（见上），但都只跑到主菜单、
  mod 加载完为止，没有跑完整局游戏；
- 真实启动器（Steam 里的 Play / dowser.exe）点下去之后的端到端还没做：那条路目前只能用
  `suspended_start_check.cpp` 复现到"导入表走完时进程还活着、恢复后游戏照常启动"（见上）；
- 多人游戏（联机一致性是钩子 mod 自己的问题，与加载方式无关）；
- Windows 11 与"系统目录不是 `C:\Windows`"的机器（转发目标写死在 def 里）；
- `d3d9.dll`（6 个）与 `winmm.dll`（1 个）的仅序号导出：只是离线核对了表格（转发到系统
  DLL 的同一个序号），没有实机用过 —— 游戏不按序号导入这两个名字；
- 其它版本的 HOI4（代理机制与版本无关，但"哪个名字、多早加载"、以及 CRT 标志位的
  形状是按 1.19.3 核的；游戏换了编译器/CRT 就用 `check_crt_probe.cpp` 重新确认，
  换了导入表就用 `check_game_imports.py` 重新确认）。

## 6. 与注入器的行为差异

| 注入器（外部） | 本 DLL 版（进程内） |
| --- | --- |
| `CreateProcess` 后等 700 ms，再远程 `LoadLibraryW` | 进程创建后等 700 ms，进程内 `LoadLibraryW` |
| `--delay` / `--probe` / `--attach` / `--wait` / `--new-instance` / `--list` | INI 的 `delay_ms` / INI 的 `probe` / 不适用 / 不适用 / 不适用 / 日志里的 `[skip]`+`loading` 行 |
| 注入失败会打印错误并保留窗口 | 写日志，游戏继续跑 |
| 需要玩家每次双击 | 随游戏启动自动生效 |
| 外部注入器原有的扫描规则 | 只加载 `injected_mods\<一级子目录>\*.dll` |

两者可以共存：`LoadLibrary` 对已加载模块返回旧句柄，`DllMain` 不会跑第二次。
