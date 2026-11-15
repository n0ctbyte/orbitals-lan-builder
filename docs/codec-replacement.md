# Python-only codec and file-safety limits

The current backend uses Python standard-library code, not a custom DLL, native
extension or subprocess. `kraken.py` implements only the needed Kraken subset,
with attribution in [THIRD-PARTY.md](../THIRD-PARTY.md).

The production codec admits only three pinned compressed SHA256/size pairs.
Decoded SHA256 and BLAKE3 digests are checked independently, and the generated
transformations have pinned regression digests. Unknown versions fail closed.
Inputs/outputs are bounded to 64 KiB for these codec calls, nested entropy RLE
depth to eight and bit/history/stream ranges are checked. Reserved long stored
entropy-header bits are rejected. This is not a generic or proven fuzz-safe
Oodle replacement. Tests contain authored synthetic data, not extracted assets.

Windows retained file handles prevent write/delete sharing while verifying and
renaming the owned output files. The output parent is retained against junction
replacement. No existing output is overwritten, no emulator is auto-configured
and no original ROM is written. These protections are why generation currently
requires Windows x64, not just any Python interpreter.

There is no atomic transaction spanning both output files. On finalization
failure the builder attempts to roll back the first file using its retained
handle; a private staging or empty output directory can remain. Such output is
never auto-activated. Other processes with the same user's permissions can alter
files after handles are released; resistance to administrators or process
injection is not claimed. Do not run the tool as administrator or disable AV.
