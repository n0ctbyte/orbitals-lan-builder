"""Bounded Zen export/name/script-reference parsing; no embedded game assets."""
from .formats import need, uint, take, bounds, put


def names_read(data, start, limit):
    count = uint(data, start)
    need(0 < count <= 150000, 'Name table exceeds limit.')
    headers = start + 16 + count * 8
    at = headers + count * 2
    bounds(headers, count * 2, limit)
    names = []
    for i in range(count):
        first = data[headers + i * 2]
        size = ((first & 127) << 8) | data[headers + i * 2 + 1]
        width = 2 if first & 128 else 1
        need(0 < size <= 32767, 'Invalid name.')
        bounds(at, size * width, limit)
        name = take(data, at, size * width).decode('utf-16-le' if width == 2 else 'utf-8', errors='strict')
        need('\0' not in name, 'Invalid name characters.')
        names.append(name)
        at += size * width
    return names, at


class Zen:
    def __init__(self, data):
        self.data = bytes(data)
        need(60 <= len(data) <= 65536, 'Zen size exceeds limit.')
        self.header, self.im, self.ex, end = (uint(data, i) for i in (4, 28, 32, 36))
        need(60 <= self.im <= self.ex < end <= self.header <= len(data) and
             (self.ex - self.im) % 8 == 0 and (end - self.ex) % 72 == 0, 'Invalid Zen header.')
        self.count = (end - self.ex) // 72
        need(0 < self.count <= 10000, 'Export count exceeds limit.')
        self.names, names_end = names_read(data, 60, self.im)
        need(names_end <= self.im, 'Names overlap imports.')
        # Script import IDs are full uint64, not signed file offsets.
        self.imports = [int.from_bytes(data[i:i + 8], 'little') for i in range(self.im, self.ex, 8)]
        self.offsets, self.lengths = [], []
        for i in range(self.count):
            at = self.ex + i * 72
            off, size = uint(data, at, 8), uint(data, at + 8, 8)
            need(0 < size <= 65536, 'Invalid export size.')
            bounds(off, size, len(data) - self.header)
            need(uint(data, at + 16) & 0x3fffffff < len(self.names), 'Invalid export name.')
            self.offsets.append(off)
            self.lengths.append(size)
        previous = 0
        for off, end in sorted((o, o + s) for o, s in zip(self.offsets, self.lengths)):
            need(off >= previous, 'Overlapping exports.')
            previous = end

    def export(self, i):
        need(0 <= i < self.count, 'Export outside table.')
        return take(self.data, self.header + self.offsets[i], self.lengths[i])

    def export_name(self, i):
        need(0 <= i < self.count, 'Export outside table.')
        return self.names[uint(self.data, self.ex + i * 72 + 16) & 0x3fffffff]

    def name_index(self, name):
        need(name in self.names, 'Required property name missing.')
        return self.names.index(name)

    def add_import(self, ident):
        need(ident >> 62 == 1, 'Expected native script reference.')
        if ident not in self.imports:
            self.imports.append(ident)
        return -self.imports.index(ident) - 1

    def rebuild(self, edits):
        need(all(0 <= i < self.count and 0 < len(b) <= 65536 for i, b in edits.items()), 'Invalid replacement.')
        order = sorted(edits, key=lambda i: self.offsets[i])
        original_imports = (self.ex - self.im) // 8
        added = (len(self.imports) - original_imports) * 8
        need(added >= 0, 'Imports cannot be removed.')
        result = bytearray(self.data[:self.ex])
        for ident in self.imports[original_imports:]:
            result += ident.to_bytes(8, 'little')
        result += self.data[self.ex:self.header]
        position = self.header
        for i in order:
            begin = self.header + self.offsets[i]
            result += self.data[position:begin] + edits[i]
            position = begin + self.lengths[i]
        result += self.data[position:]
        need(len(result) <= 65536, 'Changed resource exceeds one block.')
        put(result, 4, self.header + added)
        for field in range(32, 60, 4):
            value = uint(self.data, field)
            need(self.ex <= value <= self.header, 'Unsupported header offsets.')
            put(result, field, value + added)
        for i in range(self.count):
            shift = sum(len(edits[n]) - self.lengths[n] for n in order if self.offsets[n] < self.offsets[i])
            at = self.ex + added + i * 72
            put(result, at, self.offsets[i] + shift, 8)
            put(result, at + 8, len(edits[i]) if i in edits else self.lengths[i], 8)
        Zen(result)
        return bytes(result)


def script_objects(data):
    need(len(data) <= 10000000, 'Global metadata exceeds limit.')
    names, end = names_read(data, 0, len(data))
    count, first = uint(data, end), end + 4
    need(0 < count <= 150000 and first + count * 32 == len(data) - 8, 'Invalid script object table.')
    rows = {}
    for i in range(count):
        at = first + i * 32
        ni = uint(data, at) & 0x3fffffff
        need(ni < len(names), 'Invalid script name.')
        ident = int.from_bytes(take(data, at + 8, 8), 'little')
        outer = int.from_bytes(take(data, at + 16, 8), 'little')
        need(ident not in rows, 'Duplicate script reference.')
        rows[ident] = names[ni], outer

    def resolve(ident, seen):
        need(len(seen) < 64 and ident not in seen, 'Cyclic script reference.')
        name, outer = rows[ident]
        return (resolve(outer, seen | {ident}) + '.' if outer in rows else '') + name

    result = {}
    for ident in rows:
        path = resolve(ident, set())
        need(path not in result, 'Ambiguous native reference.')
        result[path] = ident
    return result
