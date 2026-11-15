"""Bounded, read-only NUP and IoStore metadata readers (GPL-3.0-or-later)."""
from dataclasses import dataclass
import hashlib


class InvalidData(ValueError):
    pass


def need(ok, message):
    if not ok:
        raise InvalidData(message)


def bounds(at, size, length):
    need(0 <= at <= length and 0 <= size <= length - at, 'Invalid data bounds.')


def read_exact(stream, size):
    need(0 <= size <= 32 * 1024 * 1024, 'Read exceeds limit.')
    result = bytearray()
    while len(result) < size:
        part = stream.read(size - len(result))
        need(bool(part), 'Truncated input.')
        result.extend(part)
    return bytes(result)


def sha(data):
    return hashlib.sha256(data).hexdigest()


def uint(data, at, size=4, big=False):
    bounds(at, size, len(data))
    value = int.from_bytes(data[at:at + size], 'big' if big else 'little')
    need(size != 8 or value <= 0x7fffffffffffffff, 'Integer exceeds limit.')
    return value


def put(data, at, value, size=4, big=False):
    bounds(at, size, len(data))
    need(0 <= value < 1 << (size * 8), 'Integer does not fit.')
    data[at:at + size] = value.to_bytes(size, 'big' if big else 'little')


def take(data, at, size):
    bounds(at, size, len(data))
    return bytes(data[at:at + size])


@dataclass(frozen=True)
class Member:
    name: str
    size: int
    offset: int
    stored: int
    digest: str
    codec: int


class Nup:
    def __init__(self, stream, index_sha):
        self.stream = stream
        stream.seek(0, 2)
        length = stream.tell()
        stream.seek(0)
        header = read_exact(stream, 128)
        need(header[:4] == b'NUP\x01', 'Unsupported input; original NUP required.')
        off, size = uint(header, 8, 8), uint(header, 16, 8)
        bounds(off, size, length)
        need(off >= 128 and 48 <= size <= 32 * 1024 * 1024, 'Invalid NUP index.')
        stream.seek(off)
        table = read_exact(stream, size)
        need(sha(table) == index_sha == header[24:56].hex(), 'Unsupported or altered NUP index.')
        need(uint(table, 0) == 0x01434f54, 'Unsupported NUP index type.')
        packages, dirs, files = uint(table, 4), uint(table, 8, 8), uint(table, 16, 8)
        pool, pool_size = uint(table, 24, 8), uint(table, 32, 8)
        need(packages <= 1024 and dirs <= 1000000 and files <= 1000000, 'NUP index limit exceeded.')
        first = 48 + packages * 64 + dirs * 24
        bounds(first, files * 80, size)
        bounds(pool, pool_size, size)
        need(pool >= first + files * 80, 'Overlapping NUP strings.')
        self.members = []
        for i in range(files):
            at = first + i * 80
            no, nl = uint(table, at), uint(table, at + 4)
            bounds(no, nl, pool_size)
            need(0 < nl < 1024, 'Invalid member name length.')
            name = take(table, pool + no, nl).decode('utf-8', errors='strict')
            need('\0' not in name, 'Invalid member name.')
            member = Member(name, uint(table, at + 8, 8), uint(table, at + 16, 8),
                            uint(table, at + 24, 8), take(table, at + 32, 32).hex(), table[at + 64])
            bounds(member.offset, member.stored, length)
            empty = member.offset == member.size == member.stored == member.codec == 0
            need(empty or (member.offset >= 128 and
                 (member.offset + member.stored <= off or member.offset >= off + size)),
                 'Member overlaps header or index.')
            self.members.append(member)

    def pinned(self, index, name, size, digest):
        need(0 <= index < len(self.members), 'Pinned member missing.')
        m = self.members[index]
        need((m.name, m.size, m.digest, m.codec, m.stored) == (name, size, digest, 0, size),
             'Pinned member metadata mismatch.')
        return m

    def read_at(self, member, offset, size):
        bounds(offset, size, member.size)
        self.stream.seek(member.offset + offset)
        return read_exact(self.stream, size)

    def verified(self, member, limit):
        need(member.size <= limit, 'Member exceeds limit.')
        result = self.read_at(member, 0, member.size)
        need(sha(result) == member.digest, 'Member data mismatch.')
        return result


@dataclass(frozen=True)
class Chunk:
    entry: int
    block: int
    length: int
    physical: int
    compressed: int
    digest: bytes


class Toc:
    def __init__(self, data):
        self.data = bytes(data)
        need(len(data) >= 144 and data[:16] == b'-==--==--==--==-' and
             data[16] == 8 and data[80] == 9, 'Unsupported UTOC.')
        self.header, self.entries, self.blocks = uint(data, 20), uint(data, 24), uint(data, 28)
        methods, ml = uint(data, 36), uint(data, 40)
        need(self.header == 144 and 0 < self.entries < 1000000 and self.blocks > 0 and
             uint(data, 32) == 12 and uint(data, 44) == 65536 and
             0 < methods <= 8 and 0 < ml <= 64, 'Unsupported UTOC layout.')
        self.blocks_at = self.header + self.entries * 22 + 4 * (uint(data, 84) + uint(data, 96))
        self.meta_at = len(data) - self.entries * 24
        bounds(self.blocks_at, self.blocks * 12 + methods * ml, self.meta_at)
        need(take(data, self.blocks_at + self.blocks * 12, ml).rstrip(b'\0') == b'Oodle',
             'Unsupported compression method.')

    def get(self, entry, ucas_bytes):
        need(0 <= entry < self.entries, 'Invalid chunk index.')
        at = self.header + self.entries * 12 + entry * 10
        offset, length = uint(self.data, at, 5, True), uint(self.data, at + 5, 5, True)
        need(offset % 65536 == 0 and 0 < length <= 65536, 'Unsupported multi-block chunk.')
        block = offset // 65536
        need(block < self.blocks, 'Chunk block outside TOC.')
        at = self.blocks_at + block * 12
        physical, compressed = uint(self.data, at, 5), uint(self.data, at + 5, 3)
        need(0 < compressed <= 65536 and uint(self.data, at + 8, 3) == length and
             self.data[at + 11] == 1, 'Unsupported original chunk.')
        bounds(physical, compressed, ucas_bytes)
        return Chunk(entry, block, length, physical, compressed,
                     take(self.data, self.meta_at + entry * 24, 20))

    def rewrite(self, chunks, replacements, at, hash_fn):
        need(len(chunks) == len(replacements), 'Chunk mismatch.')
        result, seen = bytearray(self.data), set()
        for c, b in zip(chunks, replacements):
            need(0 < len(b) <= 65536 and c.block not in seen, 'Unsupported replacement layout.')
            seen.add(c.block)
            put(result, self.header + self.entries * 12 + c.entry * 10 + 5, len(b), 5, True)
            ba = self.blocks_at + c.block * 12
            put(result, ba, at, 5)
            put(result, ba + 5, len(b), 3)
            put(result, ba + 8, len(b), 3)
            result[ba + 11] = 0
            digest = hash_fn(b)
            need(len(digest) == 20, 'Invalid IoHash.')
            result[self.meta_at + c.entry * 24:self.meta_at + c.entry * 24 + 24] = digest + bytes(4)
            at += len(b)
        return bytes(result)
