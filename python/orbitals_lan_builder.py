#!/usr/bin/env python3
"""Run this source with Python 3.11+ x64 on Windows. No EXE packaging."""
import argparse
import sys


def main(argv=None):
    parser = argparse.ArgumentParser(description='Local Orbitals 1.0.5 LAN-menu builder; no network or emulator activation.')
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--inspect', metavar='ORIGINAL_NUP', help='Validate metadata/compressed resources without a custom DLL or output')
    mode.add_argument('--check', metavar='ORIGINAL_NUP', help='Transform three resources only in memory using Python')
    mode.add_argument('--input', metavar='ORIGINAL_NUP', help='Build a private mod in a separate NEW output directory')
    parser.add_argument('--output', metavar='NEW_FOLDER')
    args = parser.parse_args(argv)
    if bool(args.input) != bool(args.output):
        parser.error('--input and --output must be used together')
    if sys.version_info < (3, 11) or sys.platform != 'win32':
        print('Requires Python 3.11+ x64 on Windows.', file=sys.stderr)
        return 1
    from orbitals.formats import InvalidData
    try:
        from orbitals.codec import require_backend
        codec = None if args.inspect else require_backend()
        from orbitals import builder
        if args.inspect:
            builder.inspect(args.inspect)
        elif args.check:
            builder.check(args.check, codec)
        else:
            builder.prepare(args.input, args.output, codec)
        return 0
    except (InvalidData, OSError, UnicodeError) as exc:
        # Do not echo file paths or data from OSError/decoder input to logs.
        message = str(exc) if isinstance(exc, InvalidData) else 'Read/write or path validation failed; no emulator settings were changed.'
        print('Not created: ' + message, file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print('Cancelled. Any private staging folder was not activated.', file=sys.stderr)
        return 130


if __name__ == '__main__':
    raise SystemExit(main())
