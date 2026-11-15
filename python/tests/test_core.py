import hashlib
import io
import struct
import unittest

try:
    from orbitals.formats import Nup, InvalidData, read_exact
    from orbitals.hashing import hash20
    from orbitals.codec import require_backend
except ImportError:
    Nup = None


class CoreTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Nup, 'Python bounded parser/hash/backend not implemented')

    def test_blake3_empty_and_abc(self):
        self.assertEqual(hash20(b'').hex(), 'af1349b9f5f9a1a6a0404dea36dcc9499bcb25c9')
        self.assertEqual(hash20(b'abc').hex(), '6437b3ac38465133ffb63b75273a8db548c55846')

    def test_short_reads_and_truncation(self):
        class Short(io.BytesIO):
            def read(self, n=-1):
                return super().read(min(n, 2))
        self.assertEqual(read_exact(Short(b'abc'), 3), b'abc')
        with self.assertRaises(InvalidData):
            read_exact(Short(b'abc'), 4)
        with self.assertRaises(InvalidData):
            read_exact(io.BytesIO(), 32 * 1024 * 1024 + 1)

    def test_blake3_official_block_boundaries(self):
        # Official BLAKE3-team test_vectors.json, unkeyed output prefix.
        vectors = {
            1: '2d3adedff11b61f14c886e35afa036736dcd87a7',
            63: 'e9bc37a594daad83be9470df7f7b3798297c3d83',
            64: '4eed7141ea4a5cd4b788606bd23f46e212af9cac',
            65: 'de1e5fa0be70df6d2be8fffd0e99ceaa8eb6e8c9',
            1023: '10108970eeda3eb932baac1428c7a2163b0e924c',
            1024: '42214739f095a406f3fc83deb889744ac00df831',
            1025: 'd00278ae47eb27b34faecf67b4fe263f82d54129',
            2048: 'e776b6028c7cd22a4d0ba182a8bf62205d2ef576',
            2049: '5f4d72f40d7a5f82b15ca2b2e44b1de3c2ef86c4',
            3072: 'b98cb0ff3623be03326b373de6b9095218513e64',
        }
        for size, want in vectors.items():
            with self.subTest(size=size):
                self.assertEqual(hash20(bytes(i % 251 for i in range(size))).hex(), want)
        with self.assertRaises(InvalidData):
            hash20(bytes(65537))

    def test_unknown_resource_does_not_enter_decoder(self):
        with self.assertRaisesRegex(InvalidData, 'Unrecognized compressed resource'):
            require_backend().decode(b'unknown', 1333)

    def test_nup_index_digest_and_truncated_extent(self):
        table = bytearray(48)
        struct.pack_into('<IIQQQQ', table, 0, 0x01434f54, 0, 0, 0, 48, 0)
        digest = hashlib.sha256(table).hexdigest()
        header = bytearray(128)
        header[:4] = b'NUP\x01'
        struct.pack_into('<QQ', header, 8, 128, len(table))
        header[24:56] = bytes.fromhex(digest)
        n = Nup(io.BytesIO(header + table), digest)
        self.assertEqual(n.members, [])
        with self.assertRaises(InvalidData):
            Nup(io.BytesIO(header + table[:-1]), digest)
        table[-1] ^= 1
        with self.assertRaises(InvalidData):
            Nup(io.BytesIO(header + table), digest)

    def test_nup_rejects_member_overlap(self):
        table = bytearray(129)
        struct.pack_into('<IIQQQQ', table, 0, 0x01434f54, 0, 0, 1, 128, 1)
        struct.pack_into('<IIQQQ', table, 48, 0, 1, 1, 1, 1)
        table[128] = ord('x')
        digest = hashlib.sha256(table).hexdigest()
        header = bytearray(128)
        header[:4] = b'NUP\x01'
        struct.pack_into('<QQ', header, 8, 128, len(table))
        header[24:56] = bytes.fromhex(digest)
        with self.assertRaises(InvalidData):
            Nup(io.BytesIO(header + table), digest)

    def test_utoc_rewrite_append_and_no_compression(self):
        from orbitals.formats import Toc
        b = bytearray(144 + 22 + 12 + 8 + 24)
        b[:16] = b'-==--==--==--==-'
        b[16], b[80] = 8, 9
        struct.pack_into('<7I', b, 20, 144, 1, 1, 12, 1, 8, 65536)
        b[161:166] = (3).to_bytes(5, 'big')
        b[166:171] = (5).to_bytes(5, 'little')
        b[171:174] = (2).to_bytes(3, 'little')
        b[174:177] = (3).to_bytes(3, 'little')
        b[177] = 1
        b[178:186] = b'Oodle\0\0\0'
        toc = Toc(b)
        chunk = toc.get(0, 10)
        out = toc.rewrite([chunk], [b'abc'], 100, hash20)
        self.assertEqual(out[166:178], (100).to_bytes(5, 'little') + b'\x03\0\0\x03\0\0\0')
        self.assertEqual(out[186:206].hex(), '6437b3ac38465133ffb63b75273a8db548c55846')
        self.assertEqual(out[206:210], bytes(4))
        self.assertEqual(b[177], 1)
        with self.assertRaises(InvalidData):
            toc.rewrite([chunk, chunk], [b'a', b'b'], 100, hash20)


if __name__ == '__main__':
    unittest.main()
