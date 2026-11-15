# Orbitals LAN builder

Build a minimal LAN-menu mod from your own **unmodified Orbitals Deluxe Edition
1.0.5 NUP**. The constructor is readable Python source: no packaged EXE, custom
compression DLL, `pip install`, runtime download or Steam account.

[Instrucciones en espanol](USO-ES.md) · [Codec notes](docs/codec-replacement.md)

This repository contains code and synthetic tests, **not the generated mod**.
It includes no ROM, extracted game resources, keys, firmware, profiles or saves.
The original file stays unchanged. Use only game data you are entitled to use.
This is unofficial and experimental, not a legal clearance or official support.

## Windows, macOS and Linux

| Task | Windows | macOS / Linux |
| --- | --- | --- |
| Run this constructor | Windows x64 with Python 3.11+ x64; tested | Not supported: Windows file-handle protections are required |
| Activate its generated mod in Lichii | Menu tested in an isolated Windows profile | Copy the generated files from Windows; not gameplay-validated here |

There is no native macOS/Linux generation command for this version. Do not
remove the platform checks or replace the protected writes with ordinary writes.
If you only have macOS/Linux, you currently need access to a compatible Windows
environment to generate the mod. This repository does not install Windows,
provide an emulator build or configure a VM/Wine setup.

## 1. Download the complete constructor

Choose **Code → Download ZIP** on this repository and extract it. Keep the whole
`python` folder together; the single launcher is not enough. Install Python
3.11+ x64 for Windows from [python.org](https://www.python.org/downloads/windows/)
if needed. Do not disable antivirus or run the constructor as administrator.

Open PowerShell inside the extracted repository and check Python:

```powershell
py -3 --version
py -3 -c "import struct; print(struct.calcsize('P') * 8)"
```

The version must be 3.11 or newer and the second command must print `64`.
If you use `python` instead of the Windows `py` launcher, use it consistently.

## 2. Generate the mod on Windows

Have about **7 GB of free disk space**, plus headroom. Use the exact supported
1.0.5 NUP packaging, not an NX/NSP/NSZ/XCI file renamed to `.nup`. Renaming a file
does not convert it. Other versions or layouts are deliberately rejected.

Replace the example input path with your own. The output must be a **new** folder
outside game libraries, emulator installations/profiles and linked directories.

```powershell
py -3 -B .\python\orbitals_lan_builder.py --check "D:\Games\Orbitals-original.nup"
py -3 -B .\python\orbitals_lan_builder.py --input "D:\Games\Orbitals-original.nup" --output "C:\Mods\Orbitals-LAN"
```

`--check` validates and transforms the three resources in memory without writing
a mod. Generation then streams the game container, checks the original content
and independently rereads the complete output. It does not load the whole
container into RAM. Wait for `Private mod created separately`.

The output is approximately 6.8 GB because it contains a copy of a game container,
not just the small authored menu changes. **Do not upload or redistribute it.**
If a checksum/version/path check fails, stop: do not disable the checks. Failed
generation may leave a private staging folder, which is never auto-activated.

## 3. Activate it in Lichii on Windows, macOS or Linux

Use a separate emulator profile and back up your own saves before experimenting.
The constructor does not install keys/firmware, change saves, configure controllers,
install the mod or start Lichii. Set up your game and emulator separately.

1. In the game list, right-click Orbitals and choose **Open Mod Data Location**.
   The label can vary with emulator version/language.
2. In the generated output, open `040032B023CA4000`. Copy its
   **`Minimal-Multiplayer`** folder into the mod location opened by Lichii.
   Do not add another nested title-ID folder there.
3. In the game's **Properties / Add-ons**, enable `Minimal-Multiplayer`. Disable
   other mods that replace the same menu resources; keep their files backed up.
4. Restart the game. The normal main menu should appear. Open **Multiplayer**:
   it should show **Create Game** and **Find Games**, with LAN enabled internally
   and no LAN checkbox.

The resulting layout inside the game's mod location must be:

```text
Minimal-Multiplayer/
  romfs/Orbitals/Content/Paks/
    Orbitals-Switch2.ucas
    Orbitals-Switch2.utoc
```

On macOS/Linux, transfer that generated folder privately from Windows, preserving
names and structure, then follow the same Lichii menu steps. This is a file-copy
workflow, **not a claim that the constructor runs natively on those systems**.
Compatibility still depends on the platform's Lichii build and game support;
we have not validated macOS/Linux gameplay. To undo, disable the mod in Add-ons
and restart. The original NUP is not changed.

## 4. Play through a Lichii room

Both players need matching game/update/mod versions and a compatible emulator
containing the two network fixes below. This tool supplies neither the game nor
an emulator binary.

1. The host creates a password-protected Lichii room for two players.
2. The other player joins that room. Confirm both members appear **before**
   starting the game's multiplayer flow.
3. Start Orbitals on both computers. In **Multiplayer**, the host selects
   **Create Game**; the other player selects **Find Games**, selects the host's
   session and joins. Follow the game's Ready/start prompts.
4. Keep the room connected. You can hide its panel to see the game; do not choose
   **Leave Room** or close the emulator while playing.

Rooms carry the emulated LAN traffic through ENet. The public room list is a
directory, **not an automatic hosted relay or game server**. The room host must
be reachable. On the Internet that can require the room's UDP port forwarding
or an agreed private overlay network. The usual room port is UDP `24872`, but
use the port the host actually selected. Seeing a room in the list does not
prove it is reachable. This constructor changes no firewall, VPN, router or
room settings and supplies no NAT traversal or Nintendo/Steam online services.

## The two related emulator PRs

Status checked on **15 November 2026**; use the links for later changes.

| PR | What it fixes | Status |
| --- | --- | --- |
| [1593: numeric name-info](https://github.com/zortos293/Lichii/pull/1593) | Implements bounded numeric IPv4 address/port replies for `sfdnsres` command 13; a prerequisite used during session setup | Original closed; incorporated via [1666](https://github.com/zortos293/Lichii/pull/1666), merged into `nx2` |
| [1594: proxy endpoints / ENet identity](https://github.com/zortos293/Lichii/pull/1594) | Preserves bound addresses/ports and the virtual room source identity; rejects stale queued sends after room changes | Open; do not assume ordinary released builds include it |

The constructor exposes the game's existing LAN flow; those PRs fix emulator
socket/room behavior. **Neither replaces the other.** They do not add native
Orbitals LDN, Nintendo online, a Steam backend, a relay or a per-game server.
Do not apply emulator source patches to the ROM. A newer build number alone
does not prove both fixes are present.

## Checks and limits

- `python` runtime sources unchanged from the tested Python candidate. The
  isolated Windows menu test reached Create/Host and Find/Scan. Earlier related
  emulator/mod testing reached a short initial co-op area; this is **not a
  full-game, long-session or cross-platform gameplay certification**.
- The generated override does not unlock Gallery/Deluxe entitlements or replace
  the game's online infrastructure. Experimental emulator shutdown has shown a
  guest `PANIC 499`; its cause is still under investigation, not fixed here.
- **45 synthetic tests passed on Windows**. To run them yourself:
  `cd python`, then `py -3 -B -m unittest discover -s tests -v`.
- [VirusTotal runtime-source ZIP](https://www.virustotal.com/gui/file/25c1bb0fb362a940294652e2adf24353bb0c16a49525ef37e352d9c81a9fcca4/detection):
  **0/64** on 15 November 2026. That exact 34,207-byte archive contained the ten
  runtime Python files and license, not this whole repository or the generated
  mod. Some engines did not support the file type and one timed out. An
  undetected result is not a security guarantee or a behavioral test.

## License

Authored source: GPL-3.0-or-later, see [LICENSE](LICENSE).
See [THIRD-PARTY.md](THIRD-PARTY.md) for algorithm references and upstream notices.
No game data is licensed or distributed by this project.
