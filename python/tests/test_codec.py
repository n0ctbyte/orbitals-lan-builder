import unittest
from unittest.mock import patch

from orbitals.formats import InvalidData, sha
from orbitals import codec


class CodecTests(unittest.TestCase):
    def test_default_backend_needs_no_dll(self):
        chosen = codec.require_backend()
        self.assertEqual(type(chosen).__name__, 'PythonCodec')
        with self.assertRaises(InvalidData):
            chosen.decode(b'unknown', 1333)
        chosen.close()

    def test_synthetic_admission_and_independent_output_digest(self):
        # Replace only the allowlist with authored fixture hashes; the complete
        # admission/decoder/output-check path runs. No alternate runtime option.
        frame = b'\x4c\x06ABC'
        with patch.object(codec, 'PACKED', ((sha(frame), 3),)), \
             patch.object(codec, 'RAW_SHA', (sha(b'ABC'),)):
            chosen = codec.require_backend()
            self.assertEqual(chosen.decode(frame, 3), b'ABC')
            with self.assertRaises(InvalidData):
                chosen.decode(frame[:-1] + b'X', 3)
            with patch.object(codec, 'RAW_SHA', (sha(b'wrong'),)):
                with self.assertRaises(InvalidData):
                    chosen.decode(frame, 3)

    def test_unknown_data_rejected_before_decoder(self):
        with patch('orbitals.kraken.decode', side_effect=AssertionError('decoder must not run')):
            with self.assertRaises(InvalidData):
                codec.require_backend().decode(b'\x4c\x06ABC', 3)


if __name__ == '__main__':
    unittest.main()
