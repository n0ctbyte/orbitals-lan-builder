"""Small unkeyed BLAKE3 implementation, bounded to one 64 KiB resource.

Algorithm reference: https://github.com/BLAKE3-team/BLAKE3-specs/blob/master/blake3.pdf
No third-party Python package or native codec is needed for IoHash.
This is not a general cryptographic library; keyed mode/XOF are not exposed.
"""
import struct
from .formats import need

IV = (0x6A09E667, 0xBB67AE85, 0x3C6EF372, 0xA54FF53A,
      0x510E527F, 0x9B05688C, 0x1F83D9AB, 0x5BE0CD19)
PERM = (2, 6, 3, 10, 7, 0, 4, 13, 1, 11, 12, 5, 9, 14, 15, 8)
MASK = 0xffffffff


def _compress(cv, words, counter, size, flags):
    v = list(cv) + list(IV[:4]) + [counter & MASK, counter >> 32, size, flags]

    def g(a, b, c, d, x, y):
        v[a] = (v[a] + v[b] + x) & MASK
        t = v[d] ^ v[a]
        v[d] = ((t >> 16) | (t << 16)) & MASK
        v[c] = (v[c] + v[d]) & MASK
        t = v[b] ^ v[c]
        v[b] = ((t >> 12) | (t << 20)) & MASK
        v[a] = (v[a] + v[b] + y) & MASK
        t = v[d] ^ v[a]
        v[d] = ((t >> 8) | (t << 24)) & MASK
        v[c] = (v[c] + v[d]) & MASK
        t = v[b] ^ v[c]
        v[b] = ((t >> 7) | (t << 25)) & MASK

    m = list(words)
    for _ in range(7):
        g(0, 4, 8, 12, m[0], m[1]); g(1, 5, 9, 13, m[2], m[3])
        g(2, 6, 10, 14, m[4], m[5]); g(3, 7, 11, 15, m[6], m[7])
        g(0, 5, 10, 15, m[8], m[9]); g(1, 6, 11, 12, m[10], m[11])
        g(2, 7, 8, 13, m[12], m[13]); g(3, 4, 9, 14, m[14], m[15])
        m = [m[i] for i in PERM]
    return tuple(v[i] ^ v[i + 8] for i in range(8)) + tuple(v[i + 8] ^ cv[i] for i in range(8))


def _chunk(data, counter):
    cv = IV
    blocks = [data[i:i + 64] for i in range(0, len(data), 64)] or [b'']
    for i, block in enumerate(blocks):
        flags = (1 if i == 0 else 0) | (2 if i == len(blocks) - 1 else 0)
        output = (cv, struct.unpack('<16I', block.ljust(64, b'\0')), counter, len(block), flags)
        if i != len(blocks) - 1:
            cv = _compress(*output)[:8]
    return output


def hash20(data):
    need(len(data) <= 65536, 'IoHash input exceeds limit.')
    outputs = [_chunk(data[i:i + 1024], i // 1024) for i in range(0, len(data), 1024)] or [_chunk(b'', 0)]

    def subtree(items):
        if len(items) == 1:
            return items[0]
        split = 1 << ((len(items) - 1).bit_length() - 1)
        left, right = subtree(items[:split]), subtree(items[split:])
        return IV, _compress(*left)[:8] + _compress(*right)[:8], 0, 64, 4

    cv, words, _, size, flags = subtree(outputs)
    return struct.pack('<16I', *_compress(cv, words, 0, size, flags | 8))[:20]
