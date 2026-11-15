"""Bounded Python Kraken subset. Not a generic Oodle API.

Algorithm reference: oozextract 0.5.7 (MIT), revision
8acaeb2bc375dd56c413a83aae4e87156136fdac; notices in docs/codec-replacement.md.
Scalar implementation, no SIMD, pointers, native decoder, processes or I/O.
Production admission lives in codec.py; these primitives accept synthetic tests.
"""
from .formats import need

MAX = 65536


def take(data, start, size):
    need(0 <= start <= len(data) and 0 <= size <= len(data) - start,
         'Truncated Kraken data.')
    return data[start:start + size]


def uint(data, start, size, order='big'):
    return int.from_bytes(take(data, start, size), order)


class Bits:
    """MSB table/offset bits, or LSB Huffman bits; never reads implicit padding."""
    def __init__(self, data, *, lsb=False, reverse=False):
        self.data = data[::-1] if reverse else data
        self.pos = 0
        self.lsb = lsb

    def read(self, n):
        need(0 <= n <= 32 and self.pos + n <= len(self.data) * 8,
             'Truncated Kraken bitstream.')
        result = 0
        for _ in range(n):
            byte = self.data[self.pos >> 3]
            bit = (byte >> ((self.pos & 7) if self.lsb else (7 - (self.pos & 7)))) & 1
            result = (result << 1) | bit
            self.pos += 1
        return result

    def zeros(self, limit=31):
        count = 0
        while self.read(1) == 0:
            count += 1
            need(count <= limit, 'Kraken unary code exceeds limit.')
        return count

    def used(self):
        return (self.pos + 7) // 8


def _gamma_run(bits):
    n = bits.zeros(7)
    # Old table's run code includes one extra bit after the leading1.
    return (1 << (n + 1)) + bits.read(n + 1) - 1


def _huff_table(data):
    bits = Bits(data)
    symbols = [[] for _ in range(12)]
    if bits.read(1) == 0:
        if bits.read(1) == 0:
            count = bits.read(8)
            need(count > 0, 'Empty Huffman table.')
            if count == 1:
                return None, bits.read(8), bits.used()
            width = bits.read(3)
            need(width <= 4, 'Invalid Huffman lengths.')
            seen = set()
            for _ in range(count):
                symbol, length = bits.read(8), bits.read(width) + 1
                need(length <= 11 and symbol not in seen, 'Invalid Huffman symbol.')
                seen.add(symbol)
                symbols[length].append(symbol)
        else:
            forced, skip = bits.read(2), bits.read(1)
            symbol, average, count = 0, 32, 0
            while symbol < 256:
                if skip:
                    skip = False
                else:
                    symbol += _gamma_run(bits)
                    need(symbol <= 256, 'Invalid Huffman zero run.')
                    if symbol == 256:
                        break
                run = _gamma_run(bits)
                need(symbol + run <= 256, 'Invalid Huffman run.')
                for _ in range(run):
                    n = bits.zeros(20 >> forced)
                    value = (1 << forced) + bits.read(forced) + ((n - 1) << forced)
                    length = (-(value & 1) ^ (value >> 1)) + ((average + 2) >> 2)
                    need(1 <= length <= 11, 'Invalid Huffman code length.')
                    symbols[length].append(symbol)
                    average = length + ((3 * average + 2) >> 2)
                    symbol += 1
                    count += 1
            need(count >= 2, 'Incomplete Huffman table.')
    else:
        need(bits.read(1) == 0, 'Unsupported Huffman table.')
        forced, count = bits.read(2), bits.read(8) + 1
        x = min(257 - count, count) * 2
        if count == 256:
            fluff = 0
        else:
            width = (x - 1).bit_length()
            value = bits.read(width - 1)
            z = (1 << width) - x
            fluff = value if value < z else ((value << 1) | bits.read(1)) - z
        need(count + fluff <= 512, 'Huffman range limit exceeded.')
        lengths = [bits.zeros(255) for _ in range(count + fluff)]
        for i in range(count):
            lengths[i] = (lengths[i] << forced) | bits.read(forced)
        running = 30
        for i in range(count):
            delta = -(lengths[i] & 1) ^ (lengths[i] >> 1)
            lengths[i] = delta + (running >> 2) + 1
            need(1 <= lengths[i] <= 11, 'Invalid Huffman code length.')
            running += delta
        index, symbol, used = count, 0, 0
        if fluff & 1:
            n = lengths[index]; index += 1
            need(n < 8, 'Invalid Huffman gap.')
            symbol = bits.read(n + 1) + (1 << (n + 1)) - 1
        for _ in range(fluff >> 1):
            n = lengths[index]; index += 1
            need(n < 9, 'Invalid Huffman range.')
            run = bits.read(n) + (1 << n)
            n = lengths[index]; index += 1
            need(n < 8 and used + run < count and symbol + run <= 256,
                 'Invalid Huffman symbol range.')
            gap = bits.read(n + 1) + (1 << (n + 1)) - 1
            for i in range(run):
                symbols[lengths[used + i]].append(symbol + i)
            symbol += run + gap
            used += run
        need(symbol < 256 and symbol + count - used <= 256, 'Invalid Huffman tail.')
        for i in range(count - used):
            symbols[lengths[used + i]].append(symbol + i)
    # Canonical code, read MSB-first from the LSB-oriented byte streams.
    table, code = {}, 0
    for length in range(1, 12):
        need(code + len(symbols[length]) <= 1 << length, 'Oversubscribed Huffman table.')
        for symbol in symbols[length]:
            table[length, code] = symbol
            code += 1
        code <<= 1
    need(code == 4096, 'Incomplete Huffman table.')
    return table, None, bits.used()


def _huff_streams(data, size, table):
    split = uint(data, 0, 2, 'little')
    need(0 <= split <= len(data) - 2, 'Invalid Huffman split.')
    first = Bits(data[2:2 + split], lsb=True)
    middle = Bits(data[2 + split:], lsb=True)
    back = Bits(data[2 + split:], lsb=True, reverse=True)
    streams = (first, back, middle)
    out = bytearray()
    for i in range(size):
        stream, value = streams[i % 3], 0
        for length in range(1, 12):
            value = (value << 1) | stream.read(1)
            symbol = table.get((length, value))
            if symbol is not None:
                out.append(symbol)
                break
        else:
            need(False, 'Invalid Huffman code.')
    need(first.used() == split and middle.used() + back.used() == len(data) - 2 - split,
         'Huffman streams did not meet.')
    return bytes(out)


def _huffman(data, size, kind):
    table, single, pos = _huff_table(data)
    if table is None:
        need(pos == len(data), 'Trailing Huffman single-symbol data.')
        return bytes([single]) * size
    body = data[pos:]
    if kind == 2:
        return _huff_streams(body, size, table)
    split = uint(body, 0, 3, 'little')
    need(0 < split < len(body) - 3, 'Invalid six-stream Huffman split.')
    half = (size + 1) // 2
    return (_huff_streams(body[3:3 + split], half, table) +
            _huff_streams(body[3 + split:], size - half, table))


def entropy(data, limit, depth=0):
    need(0 <= limit <= MAX and len(data) <= MAX and depth <= 8,
         'Kraken entropy limit exceeded.')
    first = uint(data, 0, 1)
    kind = (first >> 4) & 7
    if kind == 0:
        count = 2 if first >= 128 else 3
        value = uint(data, 0, count)
        need(count == 2 or (value & ~0x3ffff) == 0,
             'Reserved bits set in stored Kraken entropy header.')
        size = value & (0xfff if count == 2 else 0x3ffff)
        need(size <= limit, 'Stored entropy exceeds output limit.')
        return take(data, count, size), count + size
    if first >= 128:
        count = 3
        value = uint(data, 0, 3)
        packed = value & 1023
        size = packed + ((value >> 10) & 1023) + 1
    else:
        count = 5
        value = uint(data, 1, 4)
        packed = value & 0x3ffff
        size = (((value >> 18) | (first << 14)) & 0x3ffff) + 1
    need(0 < packed < size <= limit, 'Invalid entropy sizes.')
    payload = take(data, count, packed)
    if kind in (2, 4):
        result = _huffman(payload, size, kind)
    elif kind == 3:
        result = _rle(payload, size, depth)
    else:
        need(False, 'Unsupported Kraken entropy mode.')
    need(len(result) == size, 'Entropy output size mismatch.')
    return result, count + packed


def _rle(data, size, depth):
    if len(data) == 1:
        return data * size
    if data[0]:
        raw, used = entropy(data, MAX, depth + 1)
        data = raw + data[used:]
        need(len(data) <= MAX, 'RLE scratch limit exceeded.')
    else:
        data = data[1:]
    lo, hi, fill = 0, len(data), 0
    out = bytearray()
    while lo < hi:
        cmd = data[hi - 1]
        copy = repeat = 0
        if cmd == 0 or cmd > 47:
            hi -= 1
            copy, repeat = (~cmd) & 15, cmd >> 4
        elif cmd >= 16:
            hi -= 2
            value = uint(data, hi, 2, 'little') - 4096
            copy, repeat = value & 63, value >> 6
        elif cmd == 1:
            hi -= 1
            need(lo < hi, 'Truncated RLE fill.')
            fill = data[lo]; lo += 1
        elif cmd >= 9:
            hi -= 2
            repeat = (uint(data, hi, 2, 'little') - 0x8ff) * 128
        else:
            hi -= 2
            copy = (uint(data, hi, 2, 'little') - 511) * 64
        need(0 <= copy <= hi - lo and 0 <= repeat and len(out) + copy + repeat <= size,
             'RLE stream overrun.')
        out.extend(take(data, lo, copy)); lo += copy
        out.extend(bytes([fill]) * repeat)
    need(lo == hi and len(out) == size, 'RLE stream size mismatch.')
    return bytes(out)


def _offsets(data, packed, lengths):
    front, back = Bits(data), Bits(data, reverse=True)
    n = back.zeros(12)
    excess_count = (1 << n) + back.read(n) - 1
    need(excess_count <= 512, 'Kraken excess count limit exceeded.')
    offsets = []
    for i, value in enumerate(packed):
        width = value >> 3
        need(width <= 26, 'Kraken offset width exceeds limit.')
        extra = (front if i % 2 == 0 else back).read(width)
        offsets.append(8 - (((8 + (value & 7)) << width) | extra))
    excess = []
    for i in range(excess_count):
        bits = front if i % 2 == 0 else back
        zeros = bits.zeros(12)
        excess.append((1 << (zeros + 6)) + bits.read(zeros + 6) - 64)
    need(front.used() + back.used() == len(data), 'Kraken offset streams did not meet.')
    decoded, index = [], 0
    for value in lengths:
        if value == 255:
            need(index < len(excess), 'Missing Kraken extended length.')
            value += excess[index]; index += 1
        decoded.append(value + 3)
    need(index == len(excess), 'Unused Kraken extended lengths.')
    return offsets, decoded


def lz(data, size, mode):
    need(8 <= size <= MAX and len(data) <= MAX and mode in (0, 1), 'Invalid Kraken LZ mode/size.')
    out = bytearray(take(data, 0, 8))
    pos, streams = 8, []
    for _ in range(2):
        raw, used = entropy(data[pos:], size)
        streams.append(raw); pos += used
    need(uint(data, pos, 1) == 128, 'Unsupported Kraken offset encoding.')
    pos += 1
    for limit in (len(streams[1]), size >> 2):
        raw, used = entropy(data[pos:], limit)
        streams.append(raw); pos += used
    literals, commands, packed_offsets, packed_lengths = streams
    offsets, lengths = _offsets(data[pos:], packed_offsets, packed_lengths)
    recent, last, li, oi, ni = [0, 0, 0, -8, -8, -8, 0], -8, 0, 0, 0

    def literal_run(count):
        nonlocal li
        need(0 <= count <= len(literals) - li and len(out) + count <= size, 'Kraken literal overrun.')
        for _ in range(count):
            value = literals[li]; li += 1
            if mode == 0:
                source = len(out) + last
                need(0 <= source < len(out), 'Invalid Kraken literal history.')
                value = (value + out[source]) & 255
            out.append(value)

    for cmd in commands:
        literal, match, index = cmd & 3, (cmd >> 2) & 15, cmd >> 6
        if literal == 3:
            need(ni < len(lengths), 'Missing Kraken literal length.')
            literal = lengths[ni]; ni += 1
        recent[6] = offsets[oi] if oi < len(offsets) else 0
        literal_run(literal)
        last = recent[index + 3]
        recent[index + 1:index + 4] = recent[index:index + 3]
        recent[3] = last
        if index == 3:
            need(oi < len(offsets), 'Missing Kraken offset.')
            oi += 1
        if match == 15:
            need(ni < len(lengths), 'Missing Kraken match length.')
            match = 14 + lengths[ni]; ni += 1
        else:
            match += 2
        need(last < 0 and 0 <= len(out) + last and len(out) + match <= size,
             'Invalid Kraken match history/size.')
        for _ in range(match):
            out.append(out[len(out) + last])
    need(oi == len(offsets) and ni == len(lengths), 'Unused Kraken offsets/lengths.')
    literal_run(size - len(out))
    need(li == len(literals), 'Unused Kraken literals.')
    return bytes(out)


def decode(data, expected):
    need(isinstance(data, bytes) and 2 <= len(data) <= MAX and 0 < expected <= MAX,
         'Kraken input/output limit exceeded.')
    first, codec = data[:2]
    need((first & 63) == 12 and codec == 6, 'Unsupported Kraken frame.')
    if first & 64:
        need(len(data) == expected + 2, 'Stored Kraken size mismatch.')
        return data[2:]
    header = uint(data, 2, 3)
    packed = header & 0x3ffff
    if packed == 0x3ffff:
        need(header >> 18 == 1 and len(data) == 6, 'Invalid Kraken memset frame.')
        return data[5:6] * expected
    need(packed + 6 == len(data), 'Kraken quantum size mismatch.')
    body = data[5:]
    inner = uint(body, 0, 3)
    if not inner & 0x800000:
        raw, used = entropy(body, expected)
        need(used == len(body) and len(raw) == expected, 'Kraken entropy quantum mismatch.')
        return raw
    count, mode = inner & 0x7ffff, (inner >> 19) & 15
    need(count + 3 == len(body) and mode in (0, 1), 'Invalid Kraken inner frame.')
    if count == expected and mode == 0:
        return body[3:]
    need(count < expected, 'Invalid Kraken compressed size.')
    return lz(body[3:], expected, mode)
