import struct
import unittest
from orbitals.formats import InvalidData
try:
    from orbitals.zen import Zen
    from orbitals.transform import defaults, lifecycle, host_event, label, fs, host
except ImportError:
    Zen = None


def fixture(exports, names, export_names, imports=()):
    name_bytes = [n.encode('utf-8') for n in names]
    nm = struct.pack('<IIQ', len(names), sum(map(len, name_bytes)), 0) + bytes(8 * len(names))
    nm += b''.join(len(n).to_bytes(2, 'big') for n in name_bytes) + b''.join(name_bytes)
    im = 60 + len(nm)
    ex = im + 8 * len(imports)
    end = ex + 72 * len(exports)
    b = bytearray(end)
    struct.pack_into('<I', b, 4, end)
    struct.pack_into('<8I', b, 28, im, ex, *([end] * 6))
    b[60:im] = nm
    for i, n in enumerate(imports):
        struct.pack_into('<Q', b, im + i * 8, n)
    off = 0
    for i, e in enumerate(exports):
        struct.pack_into('<QQI', b, ex + i * 72, off, len(e), export_names[i])
        off += len(e)
    return bytes(b) + b''.join(exports) + b'SYNTHETIC_TRAILER'


class TransformTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Zen, 'Python authored transformations missing')

    def test_zen_replace_preserves_unrelated_payloads(self):
        original = fixture([b'12', b'345'], ['First', 'Second'], [0, 1])
        z = Zen(original)
        output = z.rebuild({0: b'abcd'})
        again = Zen(output)
        self.assertEqual(again.export(0), b'abcd')
        self.assertEqual(again.export(1), b'345')
        self.assertTrue(output.endswith(b'SYNTHETIC_TRAILER'))
        self.assertEqual(z.export(0), b'12')

    def test_zen_rejects_overlapping_exports(self):
        b = bytearray(fixture([b'12', b'345'], ['A', 'B'], [0, 1]))
        ex = struct.unpack_from('<I', b, 32)[0]
        struct.pack_into('<Q', b, ex + 72, 1)
        with self.assertRaises(InvalidData):
            Zen(b)

    def test_virtual_accept_inserts_only_property35_and_boolean(self):
        starts, counts = (0, 5, 8, 10, 24, 33, 49, 71, 79), (1, 2, 1, 3, 2, 1, 1, 1, 2)
        b, previous = bytearray(), 0
        for i, (start, count) in enumerate(zip(starts, counts)):
            b += struct.pack('<H', start - previous | count << 9 | (256 if i == 8 else 0))
            previous = start + count
        b += bytes(range(1, 150))
        out = defaults(bytes(b))
        self.assertEqual(len(out), 170)
        self.assertEqual(out[20:157], bytes(range(1, 138)))
        self.assertEqual(out[157], 1)
        self.assertEqual(out[158:], bytes(range(138, 150)))
        properties, p = [], 0
        for at in range(0, 20, 2):
            n = struct.unpack_from('<H', out, at)[0]
            p += n & 127
            properties.extend(range(p, p + (n >> 9)))
            p += n >> 9
        self.assertEqual(properties, [0, 5, 6, 8, 10, 11, 12, 24, 25, 33, 35, 49, 71, 79, 80])
        b[0] ^= 1
        with self.assertRaises(InvalidData):
            defaults(bytes(b))

    def test_lifecycle_lengths_and_original_return_preserved(self):
        b = bytearray(52)
        struct.pack_into('<II', b, 18, 18, 14)
        b[37:40] = b'\x04\x0b\x53'
        out = lifecycle(bytes(b), b'xyz', 7)
        self.assertEqual(struct.unpack_from('<II', out, 18), (25, 17))
        self.assertEqual(out[37:43], b'xyz\x04\x0b\x53')
        self.assertEqual(out[-12:], bytes(12))
        with self.assertRaises(InvalidData):
            lifecycle(bytes(52), b'x', 1)

    def test_ambiguous_label_refused_and_utf16_length_valid(self):
        self.assertEqual(label(b'xx' + fs('old') + b'yy', 'old', 'new'), b'xx' + fs('new') + b'yy')
        with self.assertRaises(InvalidData):
            label(fs('old') * 2, 'old', 'new')
        self.assertEqual(fs('\U0001f600')[:4], struct.pack('<i', -3))

    def test_full_front_transform_preserves_every_other_export(self):
        from orbitals.transform import front
        payload = [b'other' for _ in range(105)]
        names = ['Other', 'Temp_byte_Variable', 'DebugNetworkButton', 'ExecuteUbergraph_WBP_FrontEnd']
        ids = [0] * 105
        fn = bytearray(11907)
        struct.pack_into('<I', fn, 7080, 1)
        fn[7105:7107] = b'\x24\x01'
        struct.pack_into('<I', fn, 7148, 2)
        payload[17], payload[86], ids[17], ids[86] = bytes(fn), fs('DEBUG_NETWORK'), 3, 2
        source = fixture(payload, names, ids)
        result = Zen(front(source))
        fn[7106] = 0
        self.assertEqual(result.export(17), bytes(fn))
        self.assertEqual(result.export(86), fs('Multiplayer'))
        for i in set(range(105)) - {17, 86}:
            self.assertEqual(result.export(i), payload[i])

    def test_full_network_lifecycle_and_default_identity(self):
        from orbitals.transform import network, HOST_PATHS
        payload, ids = [b'other' for _ in range(62)], [0] * 62
        names = ['Other', 'BndEvt__WBP_FrontEndNetwork_BtnFindFriend_Synthetic',
                 'BP_OnActivated', 'Construct', 'BtnFindFriend', 'BtnFindSessions',
                 'CheckBoxIsLan', 'Default__WBP_FrontEndNetwork_C']
        event = bytearray(137)
        struct.pack_into('<II', event, 69, 36, 48)
        event[122:125] = b'\x04\x0b\x53'
        payload[6], ids[6] = bytes(event), 1
        for i in (9, 10):
            event = bytearray(52)
            struct.pack_into('<II', event, 18, 18, 14)
            event[37:40] = b'\x04\x0b\x53'
            payload[i] = bytes(event)
        ids[9], ids[10] = 2, 3
        payload[12] = b'\x01' + struct.pack('<IIIi', 1, 6, 0, -28)
        for i, text in ((42, 'オンラインロビー'), (43, 'ONLINE LOBBY'), (44, 'Lan'),
                        (45, 'Debug:'), (57, 'Find Friends')):
            payload[i] = fs(text)
        starts, counts = (0, 5, 8, 10, 24, 33, 49, 71, 79), (1, 2, 1, 3, 2, 1, 1, 1, 2)
        cdo, previous = bytearray(), 0
        for i, (start, count) in enumerate(zip(starts, counts)):
            cdo += struct.pack('<H', start - previous | count << 9 | (256 if i == 8 else 0))
            previous = start + count
        payload[55] = bytes(cdo) + bytes(range(1, 150))
        ids[55], ids[57], ids[58] = 7, 4, 5
        source = fixture(payload, names, ids, [0x4000000000000001 + i for i in range(28)])
        objects = {path: 0x4000000000000100 + i for i, path in enumerate(HOST_PATHS)}
        out = Zen(network(source, objects))
        self.assertEqual(out.export(57), fs('Create Game'))
        self.assertEqual(len(out.export(55)), 170)
        self.assertIn(b'open \0', out.export(6))
        self.assertIn(b'?listen?bIsLanMatch\0', out.export(6))
        self.assertGreater(len(out.export(9)), 52)
        for i in (0, 12, 54, 56, 58, 61):
            self.assertEqual(out.export(i), payload[i])
        wrong = list(names)
        wrong[7] = 'Default__Unrelated_C'
        with self.assertRaises(InvalidData):
            network(fixture(payload, wrong, ids, [0x4000000000000001 + i for i in range(28)]), objects)

    def test_lobby_table_keeps_unrelated_text(self):
        from orbitals.transform import table
        data = b'\0\x01\0\0\0\0' + fs('Synthetic') + struct.pack('<I', 2)
        data += fs('Lobby_Title') + fs('Play Online') + fs('Unrelated') + fs('Keep this value') + bytes(4)
        result = Zen(table(fixture([data], ['ST_UI_FrontEnd_Lobby'], [0]))).export(0)
        self.assertIn(fs('Network Game'), result)
        self.assertIn(fs('Join Game'), result)
        self.assertIn(fs('Keep this value'), result)


if __name__ == '__main__':
    unittest.main()
