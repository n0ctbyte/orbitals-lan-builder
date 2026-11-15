"""Windows x64 local-path guards. Uses OS APIs, not a custom/native codec.

Retain each checked directory object (no delete sharing), inspect opened objects
without following reparse points, and publish by retained handle without replace.
Not a boundary against administrator/process injection or post-run tampering.
"""
import ctypes as c
from ctypes import wintypes as w
import msvcrt
import os
from pathlib import Path
import time
from .formats import need

K = c.WinDLL('kernel32', use_last_error=True)
K.CreateFileW.argtypes = (w.LPCWSTR, w.DWORD, w.DWORD, c.c_void_p, w.DWORD, w.DWORD, w.HANDLE)
K.CreateFileW.restype = w.HANDLE
K.CloseHandle.argtypes = (w.HANDLE,)
K.CloseHandle.restype = w.BOOL
K.GetFileInformationByHandleEx.argtypes = (w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
K.GetFileInformationByHandleEx.restype = w.BOOL
K.GetFinalPathNameByHandleW.argtypes = (w.HANDLE, w.LPWSTR, w.DWORD, w.DWORD)
K.GetFinalPathNameByHandleW.restype = w.DWORD
K.GetDriveTypeW.argtypes = (w.LPCWSTR,)
K.GetDriveTypeW.restype = w.UINT
K.CreateDirectoryW.argtypes = (w.LPCWSTR, c.c_void_p)
K.CreateDirectoryW.restype = w.BOOL
K.SetFileInformationByHandle.argtypes = (w.HANDLE, c.c_int, c.c_void_p, w.DWORD)
K.SetFileInformationByHandle.restype = w.BOOL
BAD = c.c_void_p(-1).value


def full(path):
    text = os.fspath(path)
    need(bool(text) and '\0' not in text and not text.startswith(('\\\\', '//')),
         'Only ordinary local drive paths are supported.')
    p = Path(os.path.abspath(text))
    need(len(p.drive) == 2 and p.drive[1] == ':' and
         K.GetDriveTypeW(p.anchor) in (2, 3, 6), 'Only local drive paths are supported.')
    need(all(':' not in part and part.rstrip(' .') == part for part in p.parts[1:]),
         'Ambiguous Windows path refused.')
    need(c.sizeof(c.c_void_p) == 8, 'Only Windows x64 is supported.')
    return p


def _attributes(handle, directory):
    attr = (w.DWORD * 2)()
    need(K.GetFileInformationByHandleEx(handle, 9, attr, 8), 'Cannot inspect retained path.')
    need(not attr[0] & 0x400 and bool(attr[0] & 0x10) == directory,
         'Linked or unexpected path object refused.')


def _open(path, directory, access, share=1, create=False):
    flags = 0x00200000 | (0x02000000 if directory else 0)
    handle = K.CreateFileW(str(path), access, share, None, 1 if create else 3, flags, None)
    need(handle != BAD and handle is not None, 'Cannot retain a safe local path (Windows %d).' % c.get_last_error())
    try:
        _attributes(handle, directory)
        return handle
    except BaseException:
        K.CloseHandle(handle)
        raise


class Lease:
    def __init__(self):
        self.directories = {}

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def close(self):
        for handle in reversed(list(self.directories.values())):
            K.CloseHandle(handle)
        self.directories.clear()

    def directory(self, path, create=False, exclusive=False, movable=False):
        path = full(path)
        current = Path(path.anchor)
        sequence = [current]
        for part in path.parts[1:]:
            current /= part
            sequence.append(current)
        for current in sequence:
            key = str(current).casefold()
            leaf = current == path
            if key in self.directories:
                need(not (exclusive and leaf), 'Directory already retained.')
                continue
            if leaf and exclusive:
                need(K.CreateDirectoryW(str(current), None), 'Staging directory already exists or cannot be created.')
            elif create and not current.exists():
                need(K.CreateDirectoryW(str(current), None), 'Output ancestor changed or cannot be created.')
            access = 0xA0 | (0x10000 if leaf and movable else 0)
            self.directories[key] = _open(current, True, access)
        return path

    def read(self, path, owned_writer=False):
        path = full(path)
        self.directory(path.parent)
        handle = _open(path, False, 0x80000000, share=7 if owned_writer else 1)
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDONLY | os.O_BINARY)
        except BaseException:
            K.CloseHandle(handle)
            raise
        return os.fdopen(fd, 'rb')

    def new_file(self, path):
        path = full(path)
        self.directory(path.parent)
        handle = _open(path, False, 0xC0010000, create=True)
        try:
            fd = msvcrt.open_osfhandle(handle, os.O_RDWR | os.O_BINARY)
        except BaseException:
            K.CloseHandle(handle)
            raise
        return os.fdopen(fd, 'w+b')

    def identity(self, path):
        path = self.directory(path)
        text = c.create_unicode_buffer(2048)
        n = K.GetFinalPathNameByHandleW(self.directories[str(path).casefold()], text, 2048, 1)
        need(0 < n < 2048 and text.value.startswith('\\\\?\\Volume{'), 'Cannot resolve physical volume identity.')
        return text.value.rstrip('\\').casefold()

    @staticmethod
    def delete_owned_file(file):
        delete = w.BOOL(1)
        need(K.SetFileInformationByHandle(msvcrt.get_osfhandle(file.fileno()), 4,
                                         c.byref(delete), c.sizeof(delete)),
             'Cannot retire owned publication marker.')

    def rename_directory(self, source, target):
        source, target = full(source), full(target)
        need(source.parent == target.parent, 'Staging rename must remain in its retained parent.')
        self.directory(target.parent)
        key = str(source).casefold()
        need(key in self.directories, 'Staging directory not retained.')
        for child in list(self.directories):
            if child.startswith(key + '\\'):
                K.CloseHandle(self.directories.pop(child))
        self._rename(self.directories[key], target)
        self.directories[str(target).casefold()] = self.directories.pop(key)

    def rename_file(self, file, target):
        target = full(target)
        self.directory(target.parent)
        self._rename(msvcrt.get_osfhandle(file.fileno()), target)

    def _rename(self, handle, target):
        parent_key = str(target.parent).casefold()
        # Acquire new share-write parent before releasing the old handle. Source
        # remains retained. Callers retain a child in the destination parent,
        # keeping it nonempty and preventing reparse conversion during publish.
        replacement = _open(target.parent, True, 0xA0, share=3)
        K.CloseHandle(self.directories[parent_key])
        self.directories[parent_key] = replacement
        encoded = str(target).encode('utf-16-le')
        data = bytearray(20 + len(encoded) + 2)
        data[16:20] = len(encoded).to_bytes(4, 'little')
        data[20:20 + len(encoded)] = encoded
        info = (c.c_ubyte * len(data)).from_buffer(data)
        for attempt in range(20):
            if K.SetFileInformationByHandle(handle, 3, info, len(data)):
                return
            error = c.get_last_error()
            if error not in (5, 32, 33) or attempt == 19:
                break
            time.sleep(0.025)
        need(False, 'Cannot finalize without replacing an existing object (Windows %d).' % error)

    def remove_empty_tree(self, root):
        """Remove only known empty staging dirs, bottom-up, never recursively.

        Close each leaf immediately before rmdir while its parent is retained.
        rmdir unlinks a substituted junction, never traverses its destination;
        an unexpected file/child makes it fail rather than deleting data.
        """
        key = str(full(root)).casefold()
        owned = [p for p in self.directories if p == key or p.startswith(key + '\\')]
        for p in sorted(owned, key=len, reverse=True):
            K.CloseHandle(self.directories.pop(p))
            os.rmdir(p)


def check_output(input_path, output_path):
    source, target = full(input_path), full(output_path)
    need(len(str(target)) < 240, 'Use a shorter independent output folder.')
    need(target != Path(target.anchor) and not target.exists(), 'Output exists or is a filesystem root; nothing was replaced.')
    with Lease() as lease:
        lease.directory(source.parent)
        ancestor, tail = target, []
        while not ancestor.exists():
            tail.insert(0, ancestor.name)
            ancestor = ancestor.parent
        target_id = lease.identity(ancestor) + ''.join('\\' + s.casefold() for s in tail)
        source_root = source.parent.parent if source.parent.parent != Path(source.anchor) else source.parent
        source_id = lease.identity(source_root)
        need(target_id != source_id and not target_id.startswith(source_id + '\\'),
             'Output must be outside the source library root, including sibling folders.')
        for parent in target.parents:
            need(parent.name.casefold() not in ('roms', 'descargas', 'user'),
                 'Output must be outside game libraries and emulator profiles.')
            if not parent.exists():
                continue
            lease.directory(parent)
            markers = ('lichii.exe', 'eden-cli.exe', 'config/qt-config.ini',
                       'CMakeCache.txt', 'build/CMakeCache.txt', 'CMakeLists.txt', 'src/core/hle')
            need(not any((parent / marker).exists() for marker in markers),
                 'Output must be outside emulator installations and source/build trees.')
            need(not any(p.suffix.casefold() in ('.nup', '.nx', '.nsp', '.nsz', '.xci', '.xcz')
                         for p in parent.iterdir() if p.is_file()), 'Output must be outside directories containing games.')
    return target
