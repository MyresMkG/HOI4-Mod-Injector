# -*- coding: utf-8 -*-
r"""Build the proxy DLLs and test them without touching the game.

  1. export check: every name and ordinal of the System32 DLL must appear in the
     proxy, and every export must be a forwarder back to that file -- including
     the exports that have no name, which are forwarded by ordinal
  2. host stub: a program that imports the very functions the game imports from
     all nine names, so an unresolvable forwarder fails the test at load time
  3. loader tests: a host named hoi4.exe plus an injected_mods folder --
     the test DLL must be loaded once, bad files skipped, a foreign host name
     must be ignored, several proxies together must still load the mods once
  4. loader options: the generated INI, delay_ms and probe setting; DLLs in injected_mods itself or deeper
     than its immediate child directories must not be scanned
  5. per-DLL disable markers: sibling <DLL filename>noinject files skip loading
     before PE checks and probe handling; removing them restores loading

The loader generates injected_mods/hoi4_mod_injector.ini when missing and
reads [injector] delay_ms (default 700) and probe (default 0) on each start.

The DLLs built here land in build_out\ -- what players get is built by
build.bat into ..\..\full_releases\hoi4_mod_injector\. When both exist their
code sections are compared and a note says whether the shipped DLLs are the
ones that were just tested.

usage: py -3 tools/run_tests.py [--no-build] [--out <dir>]
       --no-build tests the DLLs already in build_out (or in --out)
       --out <dir> tests an existing build instead, e.g. the shipped DLLs
"""
import hashlib
import importlib.util
import os
import re
import shutil
import struct
import subprocess
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))          # ...\hoi4_mod_injector_src\tools
SRC = os.path.dirname(ROOT)                                # ...\hoi4_mod_injector_src
SHIPPED = os.path.join(os.path.dirname(os.path.dirname(SRC)), 'full_releases',
                       'hoi4_mod_injector')
OUT = os.path.join(SRC, 'build_out')                       # the DLLs under test
WORK = os.path.join(SRC, 'test_out')
SYS32 = r'C:\Windows\System32'
NAMES = ['dxgi', 'd3d11', 'd3d9', 'version', 'winmm',
         'opengl32', 'd3dcompiler_47', 'd3dx9_43', 'xinput1_3']
GXX = shutil.which('g++')

FAILURES = []
CHECKS = [0]


def check(condition, message):
    CHECKS[0] += 1
    if condition:
        print('  ok   %s' % message)
    else:
        print('  FAIL %s' % message)
        FAILURES.append(message)


def load_module(path, name):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gendef = load_module(os.path.join(ROOT, 'gen_proxy_def.py'), 'gendef')


def run(cmd, cwd=None, timeout=180, env=None):
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=timeout,
                          env=env)


def code_section(path):
    """md5 of the .text section: the compiled code, without the headers, the
    build timestamp and the image base the linker picks for every build."""
    data = open(path, 'rb').read()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    fh = pe + 4
    nsec, = struct.unpack_from('<H', data, fh + 2)
    optsz, = struct.unpack_from('<H', data, fh + 16)
    table = fh + 20 + optsz
    for i in range(nsec):
        if data[table + 40 * i:table + 40 * i + 8].rstrip(b'\0') != b'.text':
            continue
        _, _, raw_size, raw_at = struct.unpack_from('<IIII', data, table + 40 * i + 8)
        return hashlib.md5(data[raw_at:raw_at + raw_size]).hexdigest()
    return None


def report_shipped():
    """What players have is not necessarily what was just tested."""
    if os.path.abspath(OUT) == os.path.abspath(SHIPPED) or not os.path.isdir(SHIPPED):
        return
    print('== shipped DLLs ==')
    differ = []
    for name in NAMES:
        built = os.path.join(OUT, name + '.dll')
        shipped = os.path.join(SHIPPED, name + '.dll')
        if not os.path.exists(shipped):
            continue
        if not os.path.exists(built) or code_section(built) != code_section(shipped):
            differ.append(name)
    if differ:
        print('  NOTE ..\\..\\full_releases\\hoi4_mod_injector holds other code than the'
              ' build tested here (%s)' % ', '.join(n + '.dll' for n in differ))
        print('       run build.bat to refresh it, or'
              ' --out ..\\..\\full_releases\\hoi4_mod_injector --no-build to test it as it is')
    else:
        print('  ok   ..\\..\\full_releases\\hoi4_mod_injector holds the same code as the'
              ' build under test')


def warn_if_stale():
    """--no-build tests whatever sits in OUT; say so when the sources moved on."""
    sources = []
    for folder, endings in ((os.path.join(SRC, 'src'), ('.cpp', '.h')),
                            (os.path.join(SRC, 'def'), ('.def',))):
        sources += [os.path.join(folder, e) for e in os.listdir(folder)
                    if e.endswith(endings)]
    if not sources:
        return
    newest = max(os.path.getmtime(p) for p in sources)
    stale = [n for n in NAMES
             if os.path.exists(os.path.join(OUT, n + '.dll'))
             and os.path.getmtime(os.path.join(OUT, n + '.dll')) < newest]
    if stale:
        print('  NOTE %s in %s are older than the sources -- rebuild before trusting '
              'a green run' % (', '.join(stale), OUT))


# --------------------------------------------------------------- 1. exports

def check_exports():
    print('== export tables ==')
    for name in NAMES:
        dll = name + '.dll'
        real, real_ordinal_only = gendef.read_exports(os.path.join(SYS32, dll))
        proxy, proxy_ordinal_only = gendef.read_exports(os.path.join(OUT, dll))
        real_map = {e['name']: e['ordinal'] for e in real}
        proxy_map = {e['name']: e['ordinal'] for e in proxy}
        missing = sorted(set(real_map) - set(proxy_map))
        extra = sorted(set(proxy_map) - set(real_map))
        wrong_ord = sorted(n for n in set(real_map) & set(proxy_map)
                           if real_map[n] != proxy_map[n])
        expected = ('%s/%s' % (SYS32.replace('\\', '/'), dll)).lower()
        bad_forwarder = [e['name'] for e in proxy
                         if not e['forwarder']
                         or e['forwarder'].replace('\\', '/').lower() !=
                         ('%s.%s' % (expected, e['name'])).lower()]
        check(not missing, '%s: every name is exported (%d, missing: %s)'
              % (dll, len(real_map), missing or 'none'))
        check(not extra, '%s: no invented names (%s)' % (dll, extra or 'none'))
        check(not wrong_ord, '%s: ordinals match (%s)' % (dll, wrong_ord or 'none'))
        check(not bad_forwarder, '%s: every export forwards to System32 (%s)'
              % (dll, bad_forwarder or 'none'))
        # The exports without a name: a proxy has to carry them at the same
        # ordinal (the caller that imports them by ordinal has nothing else to
        # go by) and forward to that ordinal in the system DLL, because a
        # nameless export has no name to forward to.
        real_ord = {e['ordinal']: e for e in real_ordinal_only}
        proxy_ord = {e['ordinal']: e for e in proxy_ordinal_only}
        missing_ord = sorted(set(real_ord) - set(proxy_ord))
        bad_ord = sorted(o for o in set(real_ord) & set(proxy_ord)
                         if not proxy_ord[o]['forwarder']
                         or proxy_ord[o]['forwarder'].replace('\\', '/').lower() !=
                         ('%s.#%d' % (expected, o)).lower())
        check(not missing_ord, '%s: every ordinal-only export is there (%d, missing: %s)'
              % (dll, len(real_ord), missing_ord or 'none'))
        check(not bad_ord, '%s: the ordinal-only ones forward to that ordinal (%s)'
              % (dll, bad_ord or 'none'))


# ------------------------------------------------------------ 2. build tools

def build_tools():
    print('== build host stub and test mod ==')
    host_dir = os.path.join(WORK, 'host')
    mod_dir = os.path.join(WORK, 'mod')
    os.makedirs(host_dir, exist_ok=True)
    os.makedirs(mod_dir, exist_ok=True)
    host = os.path.join(host_dir, 'hoi4.exe')
    r = run([GXX, '-O1', '-static', '-o', host, os.path.join(ROOT, 'host_stub.cpp'),
             '-lversion', '-lwinmm', '-ldxgi', '-ld3d9', '-ld3d11', '-lopengl32',
             '-ld3dcompiler_47', '-ld3dx9_43', '-lxinput1_3'], cwd=ROOT)
    if r.returncode:
        print(r.stdout, r.stderr)
        sys.exit('cannot build the host stub')
    r = run([GXX, '-O1', '-static', '-shared', '-o', os.path.join(mod_dir, 'zz_test_mod.dll'),
             os.path.join(ROOT, 'test_mod.cpp')], cwd=ROOT)
    if r.returncode:
        print(r.stdout, r.stderr)
        sys.exit('cannot build the test mod')
    print('  host: %s' % host)


# -------------------------------------------------------------- 3. helpers

def setup_case(case, proxies, host_name='hoi4.exe', with_mods=True,
               extra_files=(), extra_dirs=(), probe=False, self_copy=False, config_text=None):
    case_dir = os.path.join(WORK, case)
    shutil.rmtree(case_dir, ignore_errors=True)
    os.makedirs(case_dir)
    for name in proxies:
        shutil.copy(os.path.join(OUT, name + '.dll'), os.path.join(case_dir, name + '.dll'))
    shutil.copy(os.path.join(WORK, 'host', 'hoi4.exe'), os.path.join(case_dir, host_name))
    if with_mods:
        mods = os.path.join(case_dir, 'injected_mods')
        mod_dir = os.path.join(mods, 'test_mod')
        os.makedirs(mod_dir)
        shutil.copy(os.path.join(WORK, 'mod', 'zz_test_mod.dll'), mod_dir)
        for source, target in extra_files:
            shutil.copy(source, os.path.join(mod_dir, target))
        for name in extra_dirs:
            os.makedirs(os.path.join(mod_dir, name))
        if self_copy:
            shutil.copy(os.path.join(OUT, proxies[0] + '.dll'),
                        os.path.join(mod_dir, proxies[0] + '.dll'))
        if probe and config_text is None:
            config_text = '[injector]\ndelay_ms=700\nprobe=1\n'
        if config_text is not None:
            with open(os.path.join(mods, 'hoi4_mod_injector.ini'), 'w', encoding='ascii') as fh:
                fh.write(config_text)
    return case_dir


def run_host(case_dir, exe='hoi4.exe', timeout=60, args=()):
    return run([os.path.join(case_dir, exe)] + list(args), cwd=case_dir, timeout=timeout)


def read(path):
    if not os.path.exists(path):
        return ''
    with open(path, 'r', encoding='utf-8', errors='replace') as fh:
        return fh.read()


def bad_files():
    """A 32-bit DLL, a text file that pretends to be one (long enough to pass the
    size check, so the MZ check is what rejects it), and a file with a good MZ
    whose header offset points nowhere."""
    syswow = os.path.join(os.environ.get('SystemRoot', r'C:\Windows'), 'SysWOW64', 'version.dll')
    broken = os.path.join(WORK, 'broken.dll')
    with open(broken, 'w', encoding='ascii') as fh:
        fh.write('this is not a PE image, it is only here to be skipped\n' * 5)
    bad_header = os.path.join(WORK, 'bad_header.dll')
    blob = bytearray(b'\0' * 0x80)
    blob[0:2] = b'MZ'                        # passes the MZ check ...
    struct.pack_into('<I', blob, 0x3c, 0)    # ... and fails on e_lfanew == 0
    with open(bad_header, 'wb') as fh:
        fh.write(bytes(blob))
    return syswow, broken, bad_header


# --------------------------------------------------------------- 4. tests

def test_each_proxy():
    print('== loader: one proxy per case ==')
    syswow, broken, bad_header = bad_files()
    for name in NAMES:
        case = setup_case('t1_' + name, [name],
                          extra_files=[(syswow, 'bad_32bit.dll'), (broken, 'broken.dll'),
                                       (bad_header, 'bad_header.dll')],
                          extra_dirs=['nested.dll'], self_copy=True)
        mods = os.path.join(case, 'injected_mods')
        mod_dir = os.path.join(mods, 'test_mod')
        deep_dir = os.path.join(mod_dir, 'deeper')
        os.makedirs(deep_dir)
        # Valid DLLs at excluded depths must neither be inspected nor loaded.
        test_dll = os.path.join(WORK, 'mod', 'zz_test_mod.dll')
        shutil.copy(test_dll, os.path.join(mods, 'root_ignored.dll'))
        shutil.copy(test_dll, os.path.join(deep_dir, 'deep_ignored.dll'))
        r = run_host(case)
        log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
        mod_log = read(os.path.join(mod_dir, 'zz_test_mod.log'))
        check(os.path.exists(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log')),
              '[%s] the loader log is inside injected_mods with the new name' % name)
        check(not os.path.exists(os.path.join(case, 'hoi4_mod_injector.log'))
              and not os.path.exists(os.path.join(case, 'hoi4_mod_loader.log'))
              and not os.path.exists(os.path.join(mods, 'hoi4_mod_loader.log')),
              '[%s] no root log or old log name is generated' % name)
        check('root_ignored.dll' not in log
              and not os.path.exists(os.path.join(mods, 'zz_test_mod.log')),
              '[%s] DLLs in injected_mods itself are ignored' % name)
        check('deep_ignored.dll' not in log
              and not os.path.exists(os.path.join(deep_dir, 'zz_test_mod.log')),
              '[%s] DLLs deeper than immediate child directories are ignored' % name)
        check(r.returncode == 0, '[%s] host ran (exit %s)' % (name, r.returncode))
        check('version size : 0' not in r.stdout and 'version size :' in r.stdout,
              '[%s] forwarded version API answered' % name)
        check('loading [1/1] zz_test_mod.dll ... ok' in log,
              '[%s] the test DLL was loaded' % name)
        check(mod_log.count('zz_test_mod loaded') == 1,
              '[%s] its DllMain ran exactly once' % name)
        check('1 of 1 DLL(s) loaded' in log, '[%s] summary line' % name)
        check('[skip] bad_32bit.dll: not an x64 DLL' in log,
              '[%s] 32-bit DLL rejected' % name)
        check('[skip] broken.dll: not a PE image' in log,
              '[%s] non-PE file rejected' % name)
        check('[skip] bad_header.dll: not a PE image (bad header offset)' in log,
              '[%s] a file with a broken header offset is rejected' % name)
        check('nested.dll' not in log and '5 candidate(s), 1 to load' in log,
              '[%s] a directory named .dll is not a candidate' % name)
        check('[skip] %s.dll: this is the loader itself' % name in log,
              '[%s] a copy of the loader in a child directory is skipped' % name)
        check('ini   :' in log and 'delay_ms=700, probe=0' in log,
              '[%s] the default configuration is logged' % name)
        ini = read(os.path.join(mods, 'hoi4_mod_injector.ini'))
        check('[injector]' in ini and 'delay_ms=700' in ini and 'probe=0' in ini
              and '; delay_ms:' in ini and '; probe:' in ini,
              '[%s] a commented default configuration is generated' % name)
        started = re.search(r'start : the message loop started \((\d+) ms into the process\)', log)
        check(started is not None,
              '[%s] the loader thread was started by the message-loop wake-up' % name)
        check(started is not None and int(started.group(1)) >= 700,
              '[%s] it was not started before the 700 ms wait (%s ms)'
              % (name, started.group(1) if started else '-'))
        check('start : the game\'s CRT was already up at attach' not in log
              and 'start : no user32' not in log,
              '[%s] no thread was started at attach' % name)
        if name == 'dxgi':
            print('       ---- %s log ----\n%s' % (name, '\n'.join(
                '       ' + line for line in log.strip().splitlines())))
            print('       ---- host output ----\n%s' % '\n'.join(
                '       ' + line for line in r.stdout.strip().splitlines()))


def test_noinject_markers():
    print('== loader: sibling dllnoinject markers ==')
    for name in NAMES:
        case = setup_case('t14_noinject_' + name, [name], probe=True)
        mods = os.path.join(case, 'injected_mods')
        disabled = os.path.join(mods, 'test_mod')
        marker = os.path.join(disabled, 'zz_test_mod.dllnoinject')
        with open(marker, 'wb'):
            pass
        with open(os.path.join(disabled, 'broken.dll'), 'wb') as fh:
            fh.write(b'not a DLL')
        with open(os.path.join(disabled, 'broken.dllnoinject'), 'w') as fh:
            fh.write('disabled')
        for folder in ['same_name', 'directory_marker']:
            mod_dir = os.path.join(mods, folder)
            os.makedirs(mod_dir)
            shutil.copy(os.path.join(WORK, 'mod', 'zz_test_mod.dll'), mod_dir)
        os.makedirs(os.path.join(mods, 'directory_marker', 'zz_test_mod.dllnoinject'))
        for suffix in ['.noinject', '.dllnoload']:
            with open(os.path.join(mods, 'same_name', 'zz_test_mod' + suffix), 'wb'):
                pass

        r = run_host(case)
        log_path = os.path.join(mods, 'hoi4_mod_injector.log')
        log = read(log_path)
        probe_flag = os.path.join(disabled, 'diplo_action_hook_probe_only.txt')
        check(r.returncode == 0, '[%s] noinject host ran' % name)
        check('[skip] zz_test_mod.dll: disabled by zz_test_mod.dllnoinject' in log,
              '[%s] an empty sibling marker skips the DLL with a reason' % name)
        check('[skip] broken.dll: disabled by broken.dllnoinject' in log,
              '[%s] noinject is checked before the PE header' % name)
        check('4 candidate(s), 2 to load' in log and '2 of 2 DLL(s) loaded' in log,
              '[%s] marker files are not candidates or counted as loadable' % name)
        check(not os.path.exists(os.path.join(disabled, 'zz_test_mod.log')),
              '[%s] the disabled DLL never ran DllMain' % name)
        check(not os.path.exists(probe_flag),
              '[%s] probe=1 does not create a flag for disabled DLLs' % name)
        for folder in ['same_name', 'directory_marker']:
            check(read(os.path.join(mods, folder, 'zz_test_mod.log')).count(
                      'zz_test_mod loaded') == 1,
                  '[%s] %s still loads its DLL' % (name, folder))
        check('probe=1' in read(os.path.join(mods, 'same_name', 'zz_test_mod.log')),
              '[%s] alternative marker suffixes do not disable loading or probe handling' % name)

        with open(os.path.join(mods, 'hoi4_mod_injector.ini'), 'w') as fh:
            fh.write('[injector]\ndelay_ms=700\nprobe=0\n')
        with open(probe_flag, 'w') as fh:
            fh.write('keep while disabled\n')
        r = run_host(case)
        check(r.returncode == 0 and read(probe_flag) == 'keep while disabled\n',
              '[%s] probe=0 preserves a disabled DLL\'s existing flag' % name)
        check(not os.path.exists(os.path.join(disabled, 'zz_test_mod.log')),
              '[%s] the DLL stays disabled on the next launch' % name)

        os.remove(marker)
        r = run_host(case)
        log = read(log_path)
        check(r.returncode == 0 and '3 of 3 DLL(s) loaded' in log,
              '[%s] removing the marker restores loading on the next launch' % name)
        check(read(os.path.join(disabled, 'zz_test_mod.log')).count(
                  'zz_test_mod loaded') == 1 and not os.path.exists(probe_flag),
              '[%s] the restored DLL runs once and normal probe handling resumes' % name)


def test_multiple_mod_dirs():
    print('== loader: multiple immediate child directories ==')
    case = setup_case('t10_children', ['dxgi'])
    # A later directory name contains an earlier DLL name. The global order
    # must still follow DLL names, and .dll directory names are valid folders.
    other_dir = os.path.join(case, 'injected_mods', 'z_other.dll')
    os.makedirs(other_dir)
    shutil.copy(os.path.join(WORK, 'mod', 'zz_test_mod.dll'),
                os.path.join(other_dir, 'aa_test_mod.DLL'))
    r = run_host(case)
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check(r.returncode == 0, 'host with multiple mod directories ran')
    check('loading [1/2] aa_test_mod.DLL ... ok' in log
          and 'loading [2/2] zz_test_mod.dll ... ok' in log,
          'DLLs from both child directories load in global file-name order')
    check(read(os.path.join(other_dir, 'zz_test_mod.log')).count('zz_test_mod loaded') == 1,
          'the DLL inside a directory named .dll loaded exactly once')
    check('2 candidate(s), 2 to load' in log and '2 of 2 DLL(s) loaded' in log,
          'the summary counts DLLs across child directories')


def test_foreign_host():
    print('== loader: a host that is not the game ==')
    case = setup_case('t2_foreign', ['dxgi'], host_name='not_the_game.exe')
    r = run_host(case, exe='not_the_game.exe')
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check(r.returncode == 0, 'the foreign host still ran (exit %s)' % r.returncode)
    check('host is not hoi4.exe; nothing to do' in log,
          'the loader refused to act outside the game')
    check(not os.path.exists(os.path.join(case, 'injected_mods', 'test_mod', 'zz_test_mod.log')),
          'no mod was loaded into the foreign host')


def test_several_proxies():
    print('== loader: three proxies at once ==')
    case = setup_case('t3_multi', ['dxgi', 'version', 'd3d11'])
    r = run_host(case)
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    mod_log = read(os.path.join(case, 'injected_mods', 'test_mod', 'zz_test_mod.log'))
    check(r.returncode == 0, 'host ran (exit %s)' % r.returncode)
    check(log.count('loading [1/1] zz_test_mod.dll ... ok (module') == 1,
          'exactly one proxy loaded the mods')
    check(log.count('was already loaded in the process') >= 2,
          'the other proxies reported the module as already loaded')
    check(mod_log.count('zz_test_mod loaded') == 1, 'DllMain still ran exactly once')


def test_probe_mode():
    print('== loader: INI probe setting ==')
    case = setup_case('t4_probe', ['dxgi'], probe=True)
    run_host(case)
    mods = os.path.join(case, 'injected_mods')
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check('probe mode: creating diplo_action_hook_probe_only.txt' in log,
          'probe mode was announced')
    check(os.path.exists(os.path.join(mods, 'test_mod', 'diplo_action_hook_probe_only.txt')),
          'diplo_action_hook_probe_only.txt was created next to the mod')
    check(not os.path.exists(os.path.join(mods, 'diplo_action_hook_probe_only.txt')),
          'the probe flag is not created in injected_mods itself')
    check('probe=1' in read(os.path.join(mods, 'test_mod', 'zz_test_mod.log')),
          'the probe flag was present when the DLL DllMain ran')
    with open(os.path.join(mods, 'hoi4_mod_injector.ini'), 'w', encoding='ascii') as fh:
        fh.write('[injector]\ndelay_ms=700\nprobe=0\n')
    run_host(case)
    check(not os.path.exists(os.path.join(mods, 'test_mod', 'diplo_action_hook_probe_only.txt')),
          'probe=0 removes the previous mod-side flag')
    check('probe=0' in read(os.path.join(mods, 'test_mod', 'zz_test_mod.log')).splitlines()[-1],
          'the flag was cleared before the next DllMain ran')


def test_missing_mods_dir():
    print('== loader: no injected_mods ==')
    case = setup_case('t5_nomods', ['dxgi'], with_mods=False)
    run_host(case)
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check('(does not exist)' in log, 'the missing folder is mentioned')
    check("create a subdirectory inside 'injected_mods' next to hoi4.exe" in log,
          'the log tells the player what to do')
    check(os.path.isfile(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log')),
          'the missing injected_mods directory is created for the log')
    check('nothing to load' in log or 'loading [' not in log,
          'no DLL was loaded')
    check('delay_ms=700' in read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.ini')),
          'a default INI is generated even when injected_mods was absent')


def test_launcher_style_wakeup():
    print('== loader: the launcher shape (no message loop, a late thread) ==')
    # Through the launcher the game is walked on a thread of its own and its own
    # message loop comes much later, so the timer the proxy arms is useless
    # there. What has to get the mods loaded is the thread attach -- and it has
    # to wait for the host to be past its start-up before it acts on it.
    case = setup_case('t8_nopump', ['dxgi'])
    r = run_host(case, args=('--no-pump',))
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check(r.returncode == 0, 'host ran (exit %s)' % r.returncode)
    check('start : a thread attached after the CRT was up' in log,
          'the thread attach is what started the loader thread')
    check('loading [1/1] zz_test_mod.dll ... ok' in log, 'the mod was loaded')


def test_ini_settings():
    print('== loader: configured delay and existing INI preservation ==')
    for label, delay in [('later', 1800), ('zero', 0)]:
        text = '; user configuration must remain unchanged\n[injector]\ndelay_ms=%d\nprobe=0\n' % delay
        case = setup_case('t11_' + label, ['dxgi'], config_text=text)
        ini_path = os.path.join(case, 'injected_mods', 'hoi4_mod_injector.ini')
        before = open(ini_path, 'rb').read()
        r = run_host(case)
        log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
        mod_log = read(os.path.join(case, 'injected_mods', 'test_mod', 'zz_test_mod.log'))
        loaded = re.search(r'uptime_ms=(\d+)', mod_log)
        check(r.returncode == 0 and '1 of 1 DLL(s) loaded' in log,
              '%s delay: the mod was loaded' % label)
        check('delay_ms=%d, probe=0' % delay in log,
              '%s delay: the configured value was read' % label)
        check(loaded is not None and int(loaded.group(1)) >= max(delay, 700),
              '%s delay: actual DllMain timing respects delay and safe startup' % label)
        check(open(ini_path, 'rb').read() == before,
              '%s delay: the existing INI is preserved byte for byte' % label)
        if delay:
            check('waiting ' in log, 'a longer delay causes the worker to wait')
        else:
            check('waiting ' not in log, 'delay_ms=0 adds no extra wait after safe startup')

    print('== loader: invalid and missing INI values ==')
    for label, text, warning in [
        ('negative', '[injector]\ndelay_ms=-1\nprobe=yes\n', True),
        ('overflow', '[injector]\ndelay_ms=4294967295\nprobe=2\n', True),
        ('text', '[injector]\ndelay_ms=oops\nprobe=oops\n', True),
        ('truncated', '[injector]\ndelay_ms=' + '0' * 80 + '1\nprobe=oops\n', True),
        ('missing_keys', '[injector]\n', False),
    ]:
        case = setup_case('t12_' + label, ['dxgi'], config_text=text)
        run_host(case)
        log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
        check('delay_ms=700, probe=0' in log and '1 of 1 DLL(s) loaded' in log,
              '%s values: defaults load the mod normally' % label)
        if warning:
            check('invalid delay_ms' in log and 'invalid probe' in log,
                  '%s values: invalid settings are reported' % label)

    print('== loader: the old probe marker is ignored ==')
    case = setup_case('t13_old_marker', ['dxgi'])
    with open(os.path.join(case, 'injected_mods', 'hoi4_mod_loader_probe.txt'), 'w') as fh:
        fh.write('')
    run_host(case)
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check('probe mode:' not in log and 'probe=0' in log,
          'the old marker does not enable probe mode')
    check('probe=0' in read(os.path.join(case, 'injected_mods', 'test_mod', 'zz_test_mod.log')),
          'the DLL observes normal mode despite the old marker')


def test_log_is_replaced():
    print('== loader: each start replaces the log ==')
    # A file an append-mode loader would have left behind, with a marker line
    # that must not survive the next start.
    case = setup_case('t9_replace', ['dxgi'])
    with open(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'), 'w', encoding='ascii') as fh:
        fh.write("[     0.000] hoi4_mod_loader 1.0 -- proxy 'dxgi.dll', pid 1234\n")
        fh.write('MARKER FROM AN EARLIER RUN\n')
    run_host(case)
    log = read(os.path.join(case, 'injected_mods', 'hoi4_mod_injector.log'))
    check('MARKER FROM AN EARLIER RUN' not in log, 'the earlier run is gone')
    check(log.count('hoi4_mod_loader 1.1 -- proxy') == 1,
          'the file holds exactly the run that just happened')
    check(log.splitlines() and 'hoi4_mod_loader 1.1' in log.splitlines()[0],
          'and it starts at its own header line')


def main():
    if GXX is None:
        sys.exit('g++ not found')
    if '--out' in sys.argv:
        i = sys.argv.index('--out')
        if i + 1 >= len(sys.argv):
            sys.exit('--out needs a directory')
        globals()['OUT'] = os.path.abspath(sys.argv[i + 1])
    print('== build ==')
    if '--no-build' not in sys.argv:
        r = run(['cmd', '/c', 'build.bat'], cwd=SRC, timeout=600,
                env=dict(os.environ, OUTDIR=OUT))
        print(r.stdout.strip()[-400:])
        if r.returncode:
            print(r.stderr)
            sys.exit('build failed')
    else:
        print('  (--no-build: testing the DLLs already in %s)' % OUT)
    for name in NAMES:
        if not os.path.exists(os.path.join(OUT, name + '.dll')):
            sys.exit('%s has no %s.dll -- build first (or pass another --out)' % (OUT, name))
    print('  testing: %s' % OUT)
    warn_if_stale()
    shutil.rmtree(WORK, ignore_errors=True)
    os.makedirs(WORK, exist_ok=True)
    check_exports()
    report_shipped()
    build_tools()
    test_each_proxy()
    test_noinject_markers()
    test_multiple_mod_dirs()
    test_foreign_host()
    test_several_proxies()
    test_probe_mode()
    test_missing_mods_dir()
    test_launcher_style_wakeup()
    test_ini_settings()
    test_log_is_replaced()
    print()
    print('%d checks, %d failure(s)' % (CHECKS[0], len(FAILURES)))
    for failure in FAILURES:
        print('  FAILED: %s' % failure)
    return 1 if FAILURES else 0


if __name__ == '__main__':
    sys.exit(main())
