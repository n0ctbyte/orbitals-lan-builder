"""Authored codec vectors; no game bytes or native reference dependency."""
import unittest

from orbitals.formats import InvalidData
try:
    from orbitals import kraken
except ImportError:
    kraken = None


def msb(text):
    return int(text.ljust((len(text) + 7) // 8 * 8, '0'), 2).to_bytes((len(text) + 7) // 8, 'big')


def stored(data):
    return len(data).to_bytes(3, 'big') + data


def entropy(kind, payload, size):
    value = ((size - 1) << 18) | len(payload)
    return bytes([(kind << 4) | (value >> 32)]) + (value & 0xffffffff).to_bytes(4, 'big') + payload


class KrakenTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(kraken, 'Pure Python Kraken decoder is missing')

    def test_stored_and_memset_frames(self):
        self.assertEqual(kraken.decode(b'\x4c\x06ABC', 3), b'ABC')
        self.assertEqual(kraken.decode(b'\x8c\x06\x07\xff\xff*', 8), b'********')

    def test_rejects_truncation_trailing_wrong_codec_and_size(self):
        frame = b'\x4c\x06ABC'
        for i in range(len(frame)):
            with self.subTest(i=i), self.assertRaises(InvalidData):
                kraken.decode(frame[:i], 3)
        for packed, size in ((frame + b'x', 3), (frame, 65537), (frame, 0),
                             (b'\x4c\x0aABC', 3), (b'\x4c\x86ABC', 3)):
            with self.subTest(size=size, packed=packed), self.assertRaises(InvalidData):
                kraken.decode(packed, size)

    def test_entropy_stored_rle_and_limits(self):
        self.assertEqual(kraken.entropy(stored(b'ABC'), 3), (b'ABC', 6))
        # RLE: cmd0x6c => copy3 followed by initial fill byte0 x6.
        self.assertEqual(kraken.entropy(entropy(3, b'\x00ABC\x6c', 9), 9)[0], b'ABC' + b'\x00' * 6)
        self.assertEqual(kraken.entropy(entropy(3, b'Z', 12), 12)[0], b'Z' * 12)
        with self.assertRaises(InvalidData):
            kraken.entropy(stored(b'ABC'), 2)
        with self.assertRaises(InvalidData):
            kraken.entropy(entropy(3, b'\x00\x00', 6), 6)

    def test_long_stored_entropy_rejects_reserved_bits(self):
        # The upper two bits of the long 18-bit size are reserved, not
        # ignorable flags. Each malformed header formerly decoded to b'A'.
        for prefix in (0x04, 0x08, 0x0c):
            with self.subTest(prefix=prefix), self.assertRaises(InvalidData):
                kraken.entropy(bytes([prefix, 0, 1, 65]), 1)
        self.assertEqual(kraken.entropy(b'\x00\x00\x01A', 1), (b'A', 4))
        self.assertEqual(kraken.entropy(b'\x80\x01A', 1), (b'A', 3))

    def test_sparse_huffman_three_interleaved_streams(self):
        # Two one-bit symbols A=0/B=1, sparse table, MSB table/LSB payload.
        table = msb('00' + '00000010' + '000' + '01000001' + '01000010')
        payload = table + b'\x02\x00' + b'\xaa\x02' + b'\xaa\x02' + b'\x05\x55'
        self.assertEqual(kraken.entropy(entropy(2, payload, 32), 32)[0], b'AB' * 16)
        with self.assertRaises(InvalidData):
            kraken.entropy(entropy(2, payload[:-1], 32), 32)

    def test_lz_modes_and_overlapping_match(self):
        # Eight initial bytes, command0 => no literals, copy2 at recent -8;
        # no explicit offsets/lengths; backwards excess count encoded as1.
        body = b'ABCDEFGH' + stored(b'') + stored(b'\x00') + b'\x80' + stored(b'') + stored(b'') + b'\x80'
        for mode in (0, 1):
            inner = (0x800000 | (mode << 19) | len(body)).to_bytes(3, 'big') + body
            packed = b'\x8c\x06' + (len(inner) - 1).to_bytes(3, 'big') + inner
            # For a tiny authored stream payload exceeds raw, so exercise LZ
            # primitive directly rather than claim this is valid frame framing.
            self.assertEqual(kraken.lz(body, 10, mode), b'ABCDEFGHAB')
        # offset -1, command255? recent index3 + match2 (0xc0), extra new
        # offset code1 => 8-(8+1)=-1; repeated byte H exercises overlap.
        body = b'ABCDEFGH' + stored(b'') + stored(b'\xc4') + b'\x80' + stored(b'\x01') + stored(b'') + b'\x80'
        self.assertEqual(kraken.lz(body, 11, 1), b'ABCDEFGHHHH')

    def test_lz_rejects_bad_history_overrun_and_unused_streams(self):
        for cmd, offset, size in ((b'\xc0', b'\x10', 10), (b'\x3c', b'', 10), (b'', b'\x01', 8)):
            body = b'ABCDEFGH' + stored(b'') + stored(cmd) + b'\x80' + stored(offset) + stored(b'') + b'\x80'
            with self.subTest(cmd=cmd), self.assertRaises(InvalidData):
                kraken.lz(body, size, 1)

    def test_offset_count_consumes_only_its_code_not_padding(self):
        self.assertEqual(kraken._offsets(b'\xc0', b'', b''), ([], []))
        self.assertEqual(kraken._offsets(b'\x8a\x40', b'', b'\xff'), ([], [263]))

    def test_new_huffman_table_and_delta_literals(self):
        # New table: symbols65/66, lengths1/1, forced Rice bits3,
        # zigzag deltas13/9, initial gap65 (unary5 + low bits2).
        table = msb('10' + '11' + '00000001' + '01' + '01' + '01' + '000001' + '101001' + '000010')
        payload = table + b'\x02\x00' + b'\xaa\x02' + b'\xaa\x02' + b'\x05\x55'
        self.assertEqual(kraken.entropy(entropy(2, payload, 32), 32)[0], b'AB' * 16)
        body = b'ABCDEFGH' + stored(b'\x01\x02\x03') + stored(b'') + b'\x80' + stored(b'') + stored(b'') + b'\x80'
        self.assertEqual(kraken.lz(body, 11, 0), b'ABCDEFGHBDF')

    def test_forward_offset_bits_and_lz_literals(self):
        body = b'ABCDEFGH' + stored(b'XY') + stored(b'\xc2') + b'\x80' + stored(b'\x08') + stored(b'') + b'\x80\x80'
        self.assertEqual(kraken.lz(body, 12, 1), b'ABCDEFGHXYBC')

    def test_dense_old_huffman_and_six_streams(self):
        # Dense old table: initial nonzero run2, code-length deltas13/9;
        # trailing zero run254. Symbols0/1 both have length1.
        dense = msb('01' + '00' + '1' + '11' + '0' * 13 + '1' + '0' * 9 + '1' + '00000011111111')
        streams = b'\x02\x00\xaa\x02\xaa\x02\x05\x55'
        self.assertEqual(kraken.entropy(entropy(2, dense + streams, 32), 32)[0], b'\x00\x01' * 16)
        table = msb('00' + '00000010' + '000' + '01000001' + '01000010')
        group = b'\x01\x00\x2a\x0a\x15'
        six = table + b'\x05\x00\x00' + group + group
        self.assertEqual(kraken.entropy(entropy(4, six, 32), 32)[0], b'AB' * 16)

    def test_full_compressed_quantum_extended_match(self):
        body = b'ABCDEFGH' + stored(b'') + stored(b'\x3c') + b'\x80' + stored(b'') + stored(b'\x19') + b'\x80'
        inner = (0x800000 | len(body)).to_bytes(3, 'big') + body
        frame = b'\x8c\x06' + (len(inner) - 1).to_bytes(3, 'big') + inner
        self.assertEqual(kraken.decode(frame, 50), b'ABCDEFGH' * 6 + b'AB')
        for i in range(len(frame)):
            with self.subTest(i=i), self.assertRaises(InvalidData):
                kraken.decode(frame[:i], 50)
        self.assertEqual(kraken.decode(b'\x8c\x06\x07\xff\xff*', 65536), b'*' * 65536)

    def test_huffman_rle_mutation_corpus_stays_bounded(self):
        table = msb('00' + '00000010' + '000' + '01000001' + '01000010')
        huff = entropy(2, table + b'\x02\x00\xaa\x02\xaa\x02\x05\x55', 32)
        for original in (huff, entropy(3, b'\x00ABC\x6c', 9)):
            cases = [original[:i] for i in range(len(original))]
            cases += [original[:i] + bytes([original[i] ^ bit]) + original[i + 1:]
                      for i in range(len(original)) for bit in (1, 8, 128)]
            for data in cases:
                try:
                    raw, used = kraken.entropy(data, 64)
                except InvalidData:
                    continue
                self.assertLessEqual(len(raw), 64)
                self.assertLessEqual(used, len(data))

    def test_recursive_rle_limit_and_malformed_corpus(self):
        import random
        nested = entropy(3, b'Z', 12)
        # Increasing declared output provides a framing-valid chain. It must
        # reject before deep recursion, rather than reaching Python recursion.
        for i in range(12):
            nested = entropy(3, nested, len(nested) + 1)
        with self.assertRaises(InvalidData):
            kraken.entropy(nested, 65536)
        random_ = random.Random(127)
        for _ in range(500):
            data = random_.randbytes(random_.randrange(0, 96))
            for operation in (kraken.entropy, kraken.decode):
                try:
                    output = operation(data, random_.randrange(1, 512))
                except InvalidData:
                    continue
                raw = output[0] if isinstance(output, tuple) else output
                self.assertLessEqual(len(raw), 511)


if __name__ == '__main__':
    unittest.main()
