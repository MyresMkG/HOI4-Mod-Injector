# -*- coding: utf-8 -*-
r"""Compare the import table of tools/host_stub.cpp against the real game exe.

The stub exists so that a forwarder which cannot be resolved fails the offline
tests at load time; for that it has to import every function the game imports
from the nine proxy names. The game's list is a property of the game build, so
this is what to run after hoi4.exe changes (or after the stub is edited):

  py -3 tools\check_game_imports.py "D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe"
  py -3 tools\check_game_imports.py <game.exe> --stub build_out\hoi4.exe

Exit code 1 when the stub is missing an import the game has (extra imports in
the stub are fine -- it links the same headers, so it pulls in more of the API).
The two ordinal imports the game makes from XINPUT1_3.dll are reported as
ORDINAL n and are checked against the stub's run-time ordinal lookup instead:
no toolchain here writes an ordinal import, so the stub cannot carry one.
"""
import os
import struct
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
SRC = os.path.dirname(HERE)
NAMES = ['version.dll', 'winmm.dll', 'd3d11.dll', 'dxgi.dll', 'd3d9.dll',
         'opengl32.dll', 'd3dcompiler_47.dll', 'd3dx9_43.dll', 'xinput1_3.dll']
DEFAULT_GAME = r'D:\SteamLibrary\steamapps\common\Hearts of Iron IV\hoi4.exe'


def read_imports(path):
    """{dll name: sorted function names} for every DLL the image imports from."""
    data = open(path, 'rb').read()
    pe = struct.unpack_from('<I', data, 0x3c)[0]
    fh = pe + 4
    nsec, = struct.unpack_from('<H', data, fh + 2)
    optsz, = struct.unpack_from('<H', data, fh + 16)
    opt = fh + 20
    is64 = struct.unpack_from('<H', data, opt)[0] == 0x20b
    so = opt + optsz
    secs = []
    for i in range(nsec):
        vsz, va, rsz, ro = struct.unpack_from('<IIII', data, so + 40 * i + 8)
        secs.append((va, max(vsz, rsz), ro))

    def r2o(rva):
        for va, vsz, ro in secs:
            if va <= rva < va + vsz:
                return ro + (rva - va)
        return None

    dd = opt + (112 if is64 else 96)
    off = r2o(struct.unpack_from('<II', data, dd + 8)[0])
    out = {}
    while True:
        ilt, ts, fc, nrva, iat = struct.unpack_from('<IIIII', data, off)
        if nrva == 0:
            break
        at = r2o(nrva)
        dll = data[at:data.find(b'\0', at)].decode('latin1')
        names = []
        t = r2o(ilt) if ilt else r2o(iat)
        while True:
            entry, = struct.unpack_from('<Q', data, t)
            if entry == 0:
                break
            if entry & 0x8000000000000000:
                names.append('ORDINAL %d' % (entry & 0xffff))
            else:
                no = r2o(entry & 0x7fffffff) + 2
                names.append(data[no:data.find(b'\0', no)].decode('latin1'))
            t += 8
        out[dll] = sorted(names)
        off += 20
    return out


def main():
    args = [a for a in sys.argv[1:]]
    stub = os.path.join(SRC, 'build_out', 'hoi4.exe')
    if '--stub' in args:
        i = args.index('--stub')
        stub = os.path.abspath(args[i + 1])
        del args[i:i + 2]
    game = args[0] if args else DEFAULT_GAME
    if not os.path.exists(game):
        sys.exit('game exe not found: %s\nusage: check_game_imports.py <game.exe> '
                 '[--stub <host_stub build>]' % game)
    if not os.path.exists(stub):
        sys.exit('%s not found -- run tools\\run_tests.py once (it builds the stub)' % stub)

    game_imports = {k.lower(): v for k, v in read_imports(game).items()}
    stub_imports = {k.lower(): v for k, v in read_imports(stub).items()}
    print('game : %s' % game)
    print('stub : %s' % stub)
    missing_total = 0
    for name in NAMES:
        have = set(game_imports.get(name, []))
        want = set(stub_imports.get(name, []))
        # The game's two ordinal imports (XINPUT1_3.dll #2 and #4): the stub
        # cannot carry an ordinal import, it looks those two ordinals up at run
        # time and compares them with the named imports of the same functions.
        ordinals = sorted(x for x in have if x.startswith('ORDINAL '))
        missing = sorted((have - want) - set(ordinals))
        missing_total += len(missing)
        print('%-18s game=%3d stub=%3d  %s%s' % (
            name, len(have), len(want),
            'ok, every game import is covered' if not missing
            else 'MISSING: %s' % ', '.join(missing),
            '  [%s: checked at run time]' % ', '.join(ordinals) if ordinals else ''))
    if missing_total:
        print('\n%d import(s) the game uses are not in the stub -- add them to '
              'tools\\host_stub.cpp' % missing_total)
        return 1
    print('\nthe stub imports every function the game imports from the nine names')
    return 0


if __name__ == '__main__':
    sys.exit(main())
