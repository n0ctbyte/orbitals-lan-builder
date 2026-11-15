import io
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

from orbitals.formats import InvalidData, sha
try:
    from orbitals.builder import write_output, MOD_PATH
except ImportError:
    write_output = None


class BuilderTests(unittest.TestCase):
    def setUp(self):
        self.assertIsNotNone(write_output, 'Python streaming output/CLI not implemented')
        scratch = Path(__file__).resolve().parents[2] / '.local'
        scratch.mkdir(exist_ok=True)
        self.temp = tempfile.TemporaryDirectory(dir=scratch)
        self.root = Path(self.temp.name)
        self.addCleanup(self.temp.cleanup)

    def test_streamed_copy_and_separate_verified_output(self):
        source = io.BytesIO(b'original payload')
        target = self.root / 'mod'
        write_output(source, 16, sha(b'original payload'), [b'one', b'two'], b'toc', target, 100000000)
        paks = target / MOD_PATH
        self.assertEqual((paks / 'Orbitals-Switch2.ucas').read_bytes(), b'original payloadonetwo')
        self.assertEqual((paks / 'Orbitals-Switch2.utoc').read_bytes(), b'toc')
        self.assertEqual(source.getvalue(), b'original payload')

    def test_wrong_checksum_never_finalizes(self):
        target = self.root / 'mod'
        with self.assertRaises(InvalidData):
            write_output(io.BytesIO(b'wrong'), 5, sha(b'right'), [b'x'], b'toc', target, 100000000)
        self.assertFalse(target.exists())

    def test_low_space_creates_no_staging(self):
        with self.assertRaises(InvalidData):
            write_output(io.BytesIO(b'x'), 1, sha(b'x'), [b'x'], b'toc', self.root / 'mod', 1)
        self.assertEqual(list(self.root.iterdir()), [])

    def test_existing_output_preserved(self):
        target = self.root / 'mod'
        target.mkdir()
        keep = target / 'keep'
        keep.write_text('keep')
        with self.assertRaises(InvalidData):
            write_output(io.BytesIO(b'x'), 1, sha(b'x'), [b'x'], b'toc', target, 100000000)
        self.assertEqual(keep.read_text(), 'keep')

    def test_cli_help_and_missing_input_without_output(self):
        cli = str(Path(__file__).resolve().parents[1] / 'orbitals_lan_builder.py')
        result = subprocess.run([sys.executable, '-B', cli, '--help'], capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('--inspect', result.stdout)
        self.assertNotIn('--codec-dll', result.stdout)
        target = self.root / 'must-not-exist'
        result = subprocess.run([sys.executable, '-B', cli, '--check', 'missing.nup'],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 1)
        self.assertIn('Cannot retain a safe local path', result.stderr)
        self.assertFalse(target.exists())

    def test_verified_files_cannot_be_written_before_directory_publish(self):
        from orbitals.windows import Lease
        original = Lease.rename_file
        attempts = []
        def attack(paths, source, target):
            # source is the retained file object; direct reopen of the same
            # object must fail before and after its publication rename.
            try:
                from orbitals.windows import K, BAD
                import ctypes
                import msvcrt
                buf = ctypes.create_unicode_buffer(2048)
                self.assertGreater(K.GetFinalPathNameByHandleW(msvcrt.get_osfhandle(source.fileno()), buf, 2048, 0), 0)
                handle = K.CreateFileW(buf.value, 0x40000000, 7, None, 3, 0x00200000, None)
                if handle != BAD:
                    K.CloseHandle(handle)
                    attempts.append('write admitted')
                else:
                    self.assertEqual(ctypes.get_last_error(), 32)
                    attempts.append('write refused')
            except OSError:
                attempts.append('write refused')
            return original(paths, source, target)
        target = self.root / 'mod'
        with patch.object(Lease, 'rename_file', attack):
            write_output(io.BytesIO(b'original'), 8, sha(b'original'), [b'x'], b'toc', target, 100000000)
        self.assertEqual(attempts, ['write refused', 'write refused'])
        self.assertEqual((target / MOD_PATH / 'Orbitals-Switch2.ucas').read_bytes(), b'originalx')

    def test_replacement_during_directory_publish_rejected_and_rolled_back(self):
        from orbitals.windows import Lease
        original = Lease.rename_file
        attacked = []
        def attack(paths, source, target):
            result = original(paths, source, target)
            if not attacked and target.name.endswith('.ucas'):
                attacked.append(True)
                victim = target
                forged = target.parent / 'forged'
                forged.write_bytes(b'forged')
                try:
                    forged.replace(victim)
                except OSError:
                    pass  # An even stronger OS refusal is also safe.
            return result
        target = self.root / 'mod'
        try:
            with patch.object(Lease, 'rename_file', attack):
                write_output(io.BytesIO(b'original'), 8, sha(b'original'), [b'x'], b'toc', target, 100000000)
        except InvalidData:
            self.assertFalse(target.exists())
        else:
            self.assertEqual((target / MOD_PATH / 'Orbitals-Switch2.ucas').read_bytes(), b'originalx')

    def test_second_file_failure_rolls_first_back_without_unlocking_it(self):
        from orbitals.windows import Lease
        original = Lease.rename_file
        calls = []
        def fail_second(paths, file, target):
            calls.append(target)
            if len(calls) == 2:
                raise InvalidData('Synthetic second move failure')
            return original(paths, file, target)
        target = self.root / 'mod'
        with patch.object(Lease, 'rename_file', fail_second), self.assertRaises(InvalidData):
            write_output(io.BytesIO(b'original'), 8, sha(b'original'), [b'x'], b'toc', target, 100000000)
        self.assertEqual(len(calls), 3)
        self.assertFalse((target / MOD_PATH / 'Orbitals-Switch2.ucas').exists())
        self.assertFalse((target / MOD_PATH / 'Orbitals-Switch2.utoc').exists())
        self.assertEqual(calls[2].read_bytes(), b'originalx')


if __name__ == '__main__':
    unittest.main()
