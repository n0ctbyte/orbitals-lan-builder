import ctypes
import os
from pathlib import Path
import tempfile
import unittest
import struct

from orbitals.formats import InvalidData
from orbitals.codec import require_backend
try:
    from orbitals.windows import Lease, check_output
except ImportError:
    Lease = None


@unittest.skipUnless(os.name == 'nt', 'Windows retained-handle guarantees')
class WindowsTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(Lease, 'Retained path protection not implemented')
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_read_only_source_and_pinned_parent(self):
        file = self.root / 'source.bin'
        file.write_bytes(b'original')
        with Lease() as lease:
            with lease.read(file) as reader:
                self.assertEqual(reader.read(), b'original')
                with self.assertRaises(OSError):
                    file.write_bytes(b'changed')
                with self.assertRaises(OSError):
                    self.root.rename(self.root.with_name(self.root.name + '-moved'))
        self.assertEqual(file.read_bytes(), b'original')

    def test_directory_rename_no_overwrite(self):
        with Lease() as lease:
            stage = self.root / 'stage'
            lease.directory(stage, create=True, exclusive=True, movable=True)
            child = stage / 'child'
            lease.directory(child, create=True)
            with lease.new_file(child / 'data') as f:
                f.write(b'ok')
            target = self.root / 'final'
            lease.rename_directory(stage, target)
        self.assertEqual((target / 'child' / 'data').read_bytes(), b'ok')
        with Lease() as lease:
            stage = self.root / 'again'
            lease.directory(stage, create=True, exclusive=True, movable=True)
            with self.assertRaises(InvalidData):
                lease.rename_directory(stage, target)
        self.assertTrue(stage.exists())

    def test_refuse_existing_library_profile_and_links(self):
        input_dir = self.root / 'library' / 'game'
        input_dir.mkdir(parents=True)
        source = input_dir / 'original.nup'
        source.write_bytes(b'x')
        self.assertEqual(check_output(source, self.root / 'out'), self.root / 'out')
        for bad in (input_dir / 'out', input_dir.parent / 'sibling', self.root):
            with self.subTest(path=bad), self.assertRaises(InvalidData):
                check_output(source, bad)
        profile = self.root / 'user'
        profile.mkdir()
        with self.assertRaises(InvalidData):
            check_output(source, profile / 'out')

    def test_reject_unknown_compressed_bytes_before_decoding(self):
        codec = require_backend()
        with self.assertRaises(InvalidData):
            codec.decode(b'unknown', 5)

    def test_junction_refused_and_parent_cannot_be_retargeted(self):
        from orbitals.windows import K, BAD
        K.DeviceIoControl.argtypes = (ctypes.c_void_p, ctypes.c_uint32, ctypes.c_void_p,
                                     ctypes.c_uint32, ctypes.c_void_p, ctypes.c_uint32,
                                     ctypes.POINTER(ctypes.c_uint32), ctypes.c_void_p)
        K.DeviceIoControl.restype = ctypes.c_int

        def set_junction(link, target):
            substitute, display = ('\\??\\' + str(target)).encode('utf-16-le'), str(target).encode('utf-16-le')
            raw = bytearray(20 + len(substitute) + len(display))
            struct.pack_into('<IHHHHHH', raw, 0, 0xA0000003, len(raw) - 8, 0, 0,
                             len(substitute), len(substitute) + 2, len(display))
            raw[16:16 + len(substitute)] = substitute
            raw[18 + len(substitute):18 + len(substitute) + len(display)] = display
            handle = K.CreateFileW(str(link), 0x40000000, 7, None, 3, 0x02200000, None)
            if handle == BAD:
                return ctypes.get_last_error()
            try:
                buffer = (ctypes.c_ubyte * len(raw)).from_buffer(raw)
                returned = ctypes.c_uint32()
                ok = K.DeviceIoControl(handle, 0x900A4, buffer, len(raw), None, 0,
                                       ctypes.byref(returned), None)
                return 0 if ok else ctypes.get_last_error()
            finally:
                K.CloseHandle(handle)

        target, link = self.root / 'target', self.root / 'link'
        target.mkdir()
        link.mkdir()
        error = set_junction(link, target)
        self.assertEqual(error, 0, 'Synthetic junction creation failed: Windows %d' % error)
        try:
            with Lease() as paths, self.assertRaises(InvalidData):
                paths.directory(link)
        finally:
            link.rmdir()  # Remove only the link, never its target.
        parent, redirect = self.root / 'parent', self.root / 'redirect'
        parent.mkdir()
        redirect.mkdir()
        with Lease() as paths:
            stage = parent / 'stage'
            paths.directory(stage, create=True, exclusive=True, movable=True)
            paths.rename_directory(stage, parent / 'final')
            self.assertNotEqual(set_junction(parent, redirect), 0)
            self.assertFalse(parent.stat(follow_symlinks=False).st_file_attributes & 0x400)


if __name__ == '__main__':
    unittest.main()
