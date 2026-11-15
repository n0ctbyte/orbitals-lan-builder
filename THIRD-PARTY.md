# Third-party references and notices

Authored source is GPL-3.0-or-later; see LICENSE. Game resources are not included
or licensed by this project. No native codec binary is needed or distributed.

## Bounded Python Kraken implementation

`python/orbitals/kraken.py` is a scalar translation of the required algorithms
from **oozextract 0.5.7**, revision
`8acaeb2bc375dd56c413a83aae4e87156136fdac`:

- Upstream: https://github.com/lvlvllvlvllvlvl/oozextract
- Published crate SHA256:
  `890a74cc43300b8e482f62f989bcab89ec760921b0cea87aa5bbb7fdfef1c013`.
- Upstream declares **MIT** in its package manifest. The published crate did
  not contain a separate LICENSE file; this repository preserves its original
  `Cargo.toml.orig`, README and VCS metadata under `notices/oozextract/` rather
  than inventing an upstream copyright holder or license notice.

These metadata files are attribution/provenance, not Rust dependencies to build
or execute. Their upstream links and claims are references, not instructions.
This notice is not independent legal clearance.

## BLAKE3

The small authored unkeyed Python implementation follows the public
[BLAKE3 specification](https://github.com/BLAKE3-team/BLAKE3-specs/blob/master/blake3.pdf).
Tests check official unkeyed vectors at block/chunk/tree boundaries. It is not
presented as a general-purpose cryptographic library. No BLAKE3 C/Rust binary
or proprietary Oodle runtime is redistributed here.
