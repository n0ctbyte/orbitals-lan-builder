"""Pinned original validation and independent, streamed mod generation."""
from contextlib import contextmanager, ExitStack
import hashlib
import os
from pathlib import Path
import shutil
import uuid
from .formats import Nup, Toc, need, sha
from .hashing import hash20
from .codec import PACKED, RAW_SHA
from .zen import script_objects
from . import transform
from .windows import Lease, check_output, full

INDEX_SHA = 'd86c3149d399f2d439be680f3f8b5d51bc54418361d0d6e0b50a391b274e71a3'
UCAS_SHA = 'e27a1e77a6c49579396159a37040117766f2a1840c4b4918a8617913bdf72e99'
CHANGED_SHA = (
    '36787f60317ee5be6a3fbf1c406196d71288ff3237fab938717503c97cde4813',
    '5ba4c591d003c7f01d16694d8942f916184b40fe4acf030138baebf3d2e9c48a',
    'c03410fc5a69e22979eb4069f195486826432cc404bdb67365870fd4922d370a',
)
MOD_PATH = Path('040032B023CA4000/Minimal-Multiplayer/romfs/Orbitals/Content/Paks')


class Original:
    def __init__(self, stream):
        self.nup = Nup(stream, INDEX_SHA)
        self.ucas = self.nup.pinned(108, 'Orbitals-Switch2.ucas', 6772785856, UCAS_SHA)
        toc = self.nup.pinned(109, 'Orbitals-Switch2.utoc', 7030463,
                              '1c7c74a31058eee1bf94bce15f0b5ffc8e7d1c38ca91d6f66469a26e685c35f3')
        self.toc = Toc(self.nup.verified(toc, 32000000))
        global_ = self.nup.pinned(105, 'global.ucas', 3344880,
                                  'c7aa1ee8c67e398c8d682195f30c3aa3b8ac458ef1170d27f56ac32f66b08487')
        self.objects = script_objects(self.nup.verified(global_, 10000000))
        self.chunks = [self.toc.get(entry, self.ucas.size) for entry in (27961, 27081, 10473)]
        self.packed = [self.nup.read_at(self.ucas, c.physical, c.compressed) for c in self.chunks]
        # All compressed resources are admitted before decoding.
        for i, (chunk, packed) in enumerate(zip(self.chunks, self.packed)):
            need((sha(packed), chunk.length) == PACKED[i], 'Original compressed resource checksum mismatch.')

    def changed(self, codec):
        raw = []
        for i, (c, packed) in enumerate(zip(self.chunks, self.packed)):
            data = codec.decode(packed, c.length)
            need(len(data) == c.length and sha(data) == RAW_SHA[i] and hash20(data) == c.digest,
                 'Original resource integrity mismatch.')
            raw.append(data)
        result = [transform.front(raw[0]), transform.network(raw[1], self.objects), transform.table(raw[2])]
        need(tuple(sha(b) for b in result) == CHANGED_SHA, 'Generated resource regression mismatch.')
        return result


@contextmanager
def open_original(path):
    with Lease() as lease:
        with lease.read(path) as stream:
            yield Original(stream)


def inspect(path):
    with open_original(path):
        print('Original 1.0.5 index, metadata and three compressed resources verified.')
        print('No codec loaded, no transformed output, no full UCAS scan.')


def check(path, codec):
    try:
        with open_original(path) as original:
            result = original.changed(codec)
            print('Original 1.0.5 verified; three resources transformed in memory.')
            for b in result:
                print('Generated resource: %d bytes; SHA256 %s' % (len(b), sha(b)))
    finally:
        codec.close()


def _verify(file, expected):
    digest = hashlib.sha256()
    file.seek(0)
    while part := file.read(8 * 1024 * 1024):
        digest.update(part)
    need(digest.hexdigest() == expected, 'Output disk verification failed.')


def write_output(source, source_bytes, expected_sha, extra, toc, target, available):
    target = full(target)
    need(0 < source_bytes <= 64 * 1024**3 and 0 < len(toc) <= 32 * 1024**2,
         'Output size exceeds limit.')
    need(all(0 < len(b) <= 65536 for b in extra), 'Invalid output resource.')
    need(available > source_bytes + sum(map(len, extra)) + len(toc) + 64 * 1024**2,
         'Insufficient free space for private output.')
    need(not target.exists(), 'Output already exists; nothing was replaced.')
    stage = target.parent / ('.orbitals-' + uuid.uuid4().hex)
    need(max(len(str(stage / MOD_PATH / 'Orbitals-Switch2.ucas')),
             len(str(target / MOD_PATH / 'Orbitals-Switch2.ucas'))) < 240,
         'Use a shorter output folder; no Windows setting needs changing.')
    with Lease() as paths:
        paths.directory(target.parent, create=True)
        need(not target.exists(), 'Output appeared; nothing was replaced.')
        paths.directory(stage, create=True, exclusive=True, movable=True)
        paks = stage / MOD_PATH
        paths.directory(paks, create=True)
        ucas, utoc = paks / 'Orbitals-Switch2.ucas', paks / 'Orbitals-Switch2.utoc'
        source_hash, whole_hash = hashlib.sha256(), hashlib.sha256()
        with ExitStack() as retained:
            f = retained.enter_context(paths.new_file(ucas))
            remaining = source_bytes
            while remaining:
                part = source.read(min(8 * 1024 * 1024, remaining))
                need(bool(part), 'Truncated source UCAS.')
                source_hash.update(part)
                whole_hash.update(part)
                f.write(part)
                remaining -= len(part)
            need(source_hash.hexdigest() == expected_sha, 'Source UCAS checksum mismatch; no mod finalized.')
            for b in extra:
                f.write(b)
                whole_hash.update(b)
            f.flush()
            os.fsync(f.fileno())
            tf = retained.enter_context(paths.new_file(utoc))
            tf.write(toc)
            tf.flush()
            os.fsync(tf.fileno())
            # Independent complete reads while original writers keep each
            # object locked against writes, deletion and pathname replacement.
            with paths.read(ucas, owned_writer=True) as reader:
                _verify(reader, whole_hash.hexdigest())
            with paths.read(utoc, owned_writer=True) as reader:
                _verify(reader, sha(toc))
            # Windows cannot rename a directory containing open files. Reserve
            # a new final tree and move the two verified objects by THEIR handles
            # instead. No file is reopened/unlocked between verify and publish.
            paths.directory(target, create=True, exclusive=True, movable=True)
            final_paks = target / MOD_PATH
            paths.directory(final_paks, create=True)
            # The first cross-directory rename needs write sharing on an
            # otherwise-empty destination parent. A retained no-delete child
            # keeps that parent nonempty, so it cannot become a junction.
            marker = retained.enter_context(paths.new_file(final_paks / '.orbitals-publish'))
            moved_ucas = False
            try:
                paths.rename_file(f, final_paks / ucas.name)
                moved_ucas = True
                paths.rename_file(tf, final_paks / utoc.name)
                paths.delete_owned_file(marker)
            except BaseException:
                if moved_ucas:
                    paths.rename_file(f, ucas)
                raise
            try:
                paths.remove_empty_tree(stage)
            except OSError:
                print('Mod verified; an empty staging folder could not be retired. No recursive cleanup was attempted.')
    # Failed staging is deliberately never activated or recursively deleted by
    # a path-based cleanup. Its unique folder is private and may remain on error.


def prepare(input_path, output_path, codec):
    try:
        target = check_output(input_path, output_path)
        with open_original(input_path) as original:
            changed = original.changed(codec)
            toc = original.toc.rewrite(original.chunks, changed, original.ucas.size, hash20)
            ancestor = target.parent
            while not ancestor.exists():
                ancestor = ancestor.parent
            available = shutil.disk_usage(ancestor).free
            # Revalidate after expensive parsing, before making any directory.
            check_output(input_path, target)
            original.nup.stream.seek(original.ucas.offset)
            write_output(original.nup.stream, original.ucas.size, UCAS_SHA, changed, toc, target, available)
        print('Private mod created separately. Original and emulator were not modified.')
        print('Generated UCAS/UTOC contain game data. Do not upload them.')
    finally:
        codec.close()
