"""Authored, version-checked menu changes. No process/OS code injection."""
from dataclasses import dataclass
import struct
from .formats import need, uint, take
from .zen import Zen


def i32(value):
    return struct.pack('<i', value)


def fs(text):
    ascii_only = text.isascii()
    b = text.encode('ascii' if ascii_only else 'utf-16-le')
    return i32(len(b) + 1 if ascii_only else -len(b) // 2 - 1) + b + bytes(1 if ascii_only else 2)


def label(data, old, value):
    before = fs(old)
    at = data.find(before)
    need(at >= 0 and data.find(before, at + len(before)) < 0, 'Missing or ambiguous label.')
    return data[:at] + fs(value) + data[at + len(before):]


@dataclass(frozen=True)
class Expression:
    data: bytes
    runtime: int


HOST_PATHS = (
    '/Script/Engine.GameplayStatics.GetGameInstance',
    '/Script/Orbitals.FrontEndFlowControllSubsystem',
    '/Script/Engine.SubsystemBlueprintLibrary.GetGameInstanceSubsystem',
    '/Script/Orbitals.OrbGameInstanceBase.GetServerTravelLevelAssetName',
    '/Script/Engine.KismetStringLibrary.Concat_StrStr',
    '/Script/Orbitals.OrbFrontEndNetwork.OnLanStateChange',
    '/Script/Orbitals.OrbGameInstanceBase.SetIsHostingSession',
    '/Script/Orbitals.FrontEndFlowControllSubsystem.SetFrontEndState',
    '/Script/Orbitals.FrontEndFlowControllSubsystem.SetIsLocalSession',
    '/Script/Engine.KismetSystemLibrary.ExecuteConsoleCommand',
    '/Script/UMG.CheckBox.SetIsChecked',
    '/Script/UMG.Widget.SetVisibility',
)


def call(refs, path, math, *args):
    need(path in refs and refs[path] < 0, 'Required native import missing.')
    return Expression(bytes([0x68 if math else 0x1c]) + i32(refs[path]) +
                      b''.join(a.data for a in args) + b'\x16', 10 + sum(a.runtime for a in args))


def context(obj, action):
    return Expression(b'\x19' + obj.data + i32(action.runtime) + bytes(8) + action.data,
                      13 + obj.runtime + action.runtime)


def host(refs):
    self_, yes, no, none = (Expression(bytes([n]), 1) for n in (0x17, 0x27, 0x28, 0x2a))
    def gi():
        return call(refs, HOST_PATHS[0], True, self_)
    def flow():
        flow_class = Expression(b'\x20' + i32(refs[HOST_PATHS[1]]), 9)
        return call(refs, HOST_PATHS[2], True, self_, flow_class)
    def string(text):
        need('\0' not in text and len(text) < 256, 'Invalid authored string.')
        b = b'\x1f' + text.encode('ascii') + b'\0'
        return Expression(b, len(b))
    map_ = context(gi(), call(refs, HOST_PATHS[3], False))
    prefix = call(refs, HOST_PATHS[4], True, string('open '), map_)
    command = call(refs, HOST_PATHS[4], True, prefix, string('?listen?bIsLanMatch'))
    actions = (
        call(refs, HOST_PATHS[5], False, yes),
        context(gi(), call(refs, HOST_PATHS[6], False, yes)),
        context(flow(), call(refs, HOST_PATHS[7], False, Expression(b'\x24\x0b', 2), yes, no)),
        context(flow(), call(refs, HOST_PATHS[8], False, no, yes)),
        call(refs, HOST_PATHS[9], True, self_, command, none),
    )
    return Expression(b''.join(a.data for a in actions) + b'\x04\x0b\x53',
                      3 + sum(a.runtime for a in actions))


def lan(refs, name_index, owner):
    field = Expression(b'\x01' + i32(1) + i32(name_index) + bytes(4) + i32(owner), 9)
    actions = (
        context(field, call(refs, HOST_PATHS[10], False, Expression(b'\x27', 1))),
        call(refs, HOST_PATHS[5], False, Expression(b'\x27', 1)),
        context(field, call(refs, HOST_PATHS[11], False, Expression(b'\x24\x01', 2))),
    )
    return Expression(b''.join(a.data for a in actions), sum(a.runtime for a in actions))


def defaults(data):
    starts, counts = (0, 5, 8, 10, 24, 33, 49, 71, 79), (1, 2, 1, 3, 2, 1, 1, 1, 2)
    need(len(data) == 167, 'Unsupported network default size.')
    previous = 0
    for i, (start, count) in enumerate(zip(starts, counts)):
        fragment = start - previous | count << 9 | (256 if i == 8 else 0)
        need(uint(data, i * 2, 2) == fragment, 'Unsupported network default schema.')
        previous = start + count
    output, previous, inserted = bytearray(), 0, False
    for i, (start, count) in enumerate(zip(starts, counts)):
        if not inserted and start > 35:
            output += struct.pack('<H', 35 - previous | 1 << 9)
            previous, inserted = 36, True
        output += struct.pack('<H', start - previous | count << 9 | (256 if i == 8 else 0))
        previous = start + count
    return bytes(output) + data[18:155] + b'\x01' + data[155:]


def lifecycle(data, actions, runtime):
    need(len(data) == 52 and uint(data, 18) == 18 and uint(data, 22) == 14 and
         data[37:40] == b'\x04\x0b\x53' and actions and runtime > 0, 'Unsupported lifecycle callback.')
    return data[:18] + i32(18 + runtime) + i32(14 + len(actions)) + data[26:37] + actions + data[37:]


def host_event(data, code, runtime):
    need(len(data) == 137 and uint(data, 69) == 36 and uint(data, 73) == 48 and
         data[122:125] == b'\x04\x0b\x53' and code and runtime > 0, 'Unsupported original host callback.')
    return data[:69] + i32(runtime) + i32(len(code)) + code + data[125:]


def front(data):
    z = Zen(data)
    need(z.count == 105 and z.export_name(17) == 'ExecuteUbergraph_WBP_FrontEnd' and
         z.export_name(86) == 'DebugNetworkButton', 'Unsupported front-end layout.')
    fn = bytearray(z.export(17))
    need(len(fn) == 11907 and fn[7105:7107] == b'\x24\x01', 'Unexpected visibility instruction.')
    need(fn.find(i32(z.name_index('Temp_byte_Variable')), 7060, 7105) >= 0 and
         fn.find(i32(z.name_index('DebugNetworkButton')), 7107, 7168) >= 0,
         'Visibility instruction targets another property.')
    fn[7106] = 0
    return z.rebuild({17: bytes(fn), 86: label(z.export(86), 'DEBUG_NETWORK', 'Multiplayer')})


def network(data, objects):
    z = Zen(data)
    need(z.count == 62 and z.export_name(6).startswith('BndEvt__WBP_FrontEndNetwork_BtnFindFriend_') and
         all(z.export_name(i) == n for i, n in ((9, 'BP_OnActivated'), (10, 'Construct'),
             (55, 'Default__WBP_FrontEndNetwork_C'), (57, 'BtnFindFriend'), (58, 'BtnFindSessions'))),
         'Unsupported network widget.')
    need(all(p in objects for p in HOST_PATHS), 'Required native function unavailable.')
    refs = {p: z.add_import(objects[p]) for p in HOST_PATHS}
    emitted = host(refs)
    check_name = z.name_index('CheckBoxIsLan')
    field = b'\x01' + i32(1) + i32(check_name) + bytes(4) + i32(-28)
    need((z.ex - z.im) // 8 >= 28 and field in z.export(12), 'Unsupported checkbox owner.')
    init = lan(refs, check_name, -28)
    edits = {6: host_event(z.export(6), emitted.data, emitted.runtime),
             9: lifecycle(z.export(9), init.data, init.runtime),
             10: lifecycle(z.export(10), init.data, init.runtime),
             55: defaults(z.export(55))}
    for i, old, value in ((42, 'オンラインロビー', ' '), (43, 'ONLINE LOBBY', 'Multiplayer'),
                          (44, 'Lan', ' '), (45, 'Debug:', ' '), (57, 'Find Friends', 'Create Game')):
        edits[i] = label(z.export(i), old, value)
    return z.rebuild(edits)


def table(data):
    z = Zen(data)
    need(z.count == 1 and z.export_name(0) == 'ST_UI_FrontEnd_Lobby', 'Unsupported lobby table.')
    b = z.export(0)
    need(len(b) > 10 and b[:6] == b'\x00\x01\x00\x00\x00\x00', 'Unsupported table properties.')
    at = 6
    def read_fs():
        nonlocal at
        size = uint(b, at)
        at += 4
        need(0 < size <= 4097, 'Unsupported string-table encoding.')
        raw = take(b, at, size)
        need(raw[-1] == 0 and b'\0' not in raw[:-1], 'Invalid table string.')
        at += size
        return raw[:-1].decode('utf-8', errors='strict')
    read_fs()
    count_at = at
    count = uint(b, at)
    at += 4
    need(0 < count < 1000, 'Invalid table count.')
    pairs, keys = [], set()
    for _ in range(count):
        key, value = read_fs(), read_fs()
        need(key not in keys, 'Duplicate table key.')
        keys.add(key)
        if key == 'Lobby_Title':
            need(value == 'Play Online', 'Unexpected lobby title.')
            value = 'Network Game'
        pairs.append((key, value))
    need(at + 4 == len(b) and uint(b, at) == 0 and 'Lobby_Title' in keys and
         'DebugLobby_Button_Join' not in keys, 'Unsupported table trailer or join key.')
    pairs.append(('DebugLobby_Button_Join', 'Join Game'))
    changed = b[:count_at] + i32(len(pairs)) + b''.join(fs(k) + fs(v) for k, v in pairs) + bytes(4)
    return z.rebuild({0: changed})
