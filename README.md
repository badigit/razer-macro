# Razer Macro

Remap the **M1–M5 macro keys** on Razer keyboards without Razer Synapse.
Single ~5 MB executable, no drivers, no background bloat, ~10 MB of RAM.

[Русская версия](README.ru.md)

Built and tested on a **BlackWidow Ultimate 2013** (`1532:011A`). Other models
that speak the same protocol should work — see [Other models](#other-models).

## Why

The M-keys send nothing that Windows can see. They only come alive when the
keyboard is switched into **driver mode**, which is what Synapse does — along
with an account, a launcher and a few hundred megabytes of resident services.

This is the same job in a single file: put the keyboard into driver mode,
listen for macro-key reports, inject keystrokes via `SendInput`.

## Install

1. Grab `razer-macro-windows-x64.zip` from [Releases](../../releases) and unpack
   it anywhere — `%LOCALAPPDATA%\Programs\razer-macro` is a good spot.
2. Run `razer-macro.exe`. It lands in the tray and writes a `config.toml`
   next to itself on first start.
3. Autostart: tick **Start with Windows** in the tray menu, or run
   `razer-macro.exe --install` (`--uninstall` to undo).

Either way it writes one value under
`HKCU\Software\Microsoft\Windows\CurrentVersion\Run` — no admin rights, no
scheduled task, no startup shortcut. The tray checkbox reads the registry every
time the menu opens, so it always shows the real state.

**Close or uninstall Synapse first** — two programs cannot own the device at once.

Windows SmartScreen will warn about an unsigned binary; code signing certificates
cost money and this project has none. Build it yourself if that matters to you.

## Configure

Edit `config.toml`, then pick **Reload config** from the tray menu.

```toml
[keyboard]
vendor_id = "0x1532"
product_id = "0x011A"

[binds]
M1 = "^+{PRINTSCREEN}"   # Ctrl+Shift+PrtScrn
M3 = "{PRINTSCREEN}"     # PrtScrn
M5 = "#+s"               # Win+Shift+S
# M4 = "run:notepad.exe" # launch a program instead
```

Modifiers go at the front: `^` Ctrl, `!` Alt, `+` Shift, `#` Win.
Named keys go in braces — `{PRINTSCREEN}`, `{F13}`, `{VOLUME_UP}`, `{DELETE}`,
arrows, media keys. Latin letters, digits and signs resolve to the physical
key (US layout); Cyrillic letters map through ЙЦУКЕН (й = the Q key), so
hotkeys fire no matter which keyboard layout is active.

### Key numbering is mirrored

The M1–M5 labels run **bottom to top**, but the codes the keyboard sends run
**top to bottom**. Worth knowing before you wonder why the wrong key fired:

| Label | M5 (top) | M4 | M3 (middle) | M2 | M1 (bottom) |
|-------|----------|----|-------------|----|-------------|
| Code  | `0x20`   | `0x21` | `0x22`  | `0x23` | `0x24`  |

You can bind raw codes instead of labels — `0x21 = "{VOLUME_UP}"`.

## How it works

1. Enumerate the keyboard's HID interfaces through SetupAPI.
2. Send a **set device mode** feature report (`class 0x00`, `id 0x04`, mode `0x03`)
   and read it back with `0x84`. Whichever interface answers `0x03` is the
   control interface — found by probing, not hardcoded.
3. Read input reports from the vendor collection (`Col04`). A macro report is
   `04 <code> …`, and it lists **every** key currently held, so presses are
   detected as a set difference rather than a single byte.
4. Inject the bound combination with `SendInput`.
5. On exit: restore **normal mode**, release stuck modifiers, close handles.

The read loop blocks on overlapped I/O and a stop event, so an idle daemon costs
no CPU at all — no polling.

### Other models

Run `razer-macro.exe --list` to see every Razer HID interface with its VID/PID,
then put yours in `config.toml`. If your model uses a different transaction id
than `0xFF`, the mode switch will fail — open an issue with the `--list` output.

## Memory

Measured on Windows 11, Python 3.14 build:

| Build | Processes | Working set | Private |
|-------|-----------|-------------|---------|
| folder (`razer-macro-windows-x64.zip`) | 1 | ~27 MB | ~15 MB |
| single file (`razer-macro.exe`) | 2 | ~35 MB | ~16 MB |

**The folder build is the lean one.** A one-file PyInstaller binary unpacks
itself to a temp directory and keeps the bootloader process alive alongside the
interpreter — convenient, but that is the extra ~9 MB. The single exe is offered
for people who want one file and don't care.

What keeps it at 27 MB rather than 60:

- **No pystray, no Pillow.** The tray icon is drawn straight into a DIB section
  and handed to `Shell_NotifyIcon`, so the whole GUI is ctypes.
- **No hidapi.** HID goes through `setupapi`/`hid.dll` directly, which also means
  no bundled native DLL.
- Unused HID interfaces are closed once the control and macro collections are
  identified.
- `SetProcessWorkingSetSize` after startup and every five minutes — the daemon
  sleeps almost always, so pages taken during init go back to the system.

The floor here is CPython itself. Getting materially below this means not being
a Python program.

## Build

```
pip install pyinstaller
python -m PyInstaller --clean --noconfirm razer-macro.spec
```

Output: `dist\razer-macro.exe`. Tagging `v*` builds it on CI and attaches the
zip to a GitHub release.

Running from source needs nothing but Python 3.11+ (`tomllib`):

```
python razer-macro.py --console
```

## Troubleshooting

Log: `%LOCALAPPDATA%\razer-macro\daemon.log`.

- **Nothing happens.** Is Synapse running? Does `--list` show the keyboard?
- **A hotkey with modifiers is ignored** while the bare key works — the receiver
  is checking for `KEYEVENTF_EXTENDEDKEY`. Extended keys are listed in
  `EXTENDED_VKS` (keys.py); add yours there.
- **Keyboard went silent after a hard kill.** Driver mode was never rolled back —
  replug the USB cable.

## Credits

The wire format — report layout, XOR checksum, the device-mode command — was
understood from the [OpenRazer](https://github.com/openrazer/openrazer) project.
No OpenRazer code is used here; this is an independent implementation. Thanks to
its authors for documenting the hardware.

## Trademarks

This is an independent, unofficial project. It is **not affiliated with,
endorsed by, or supported by Razer Inc.** "Razer", "BlackWidow" and "Synapse"
are trademarks of Razer Inc., used here only to describe which hardware this
software works with. No Razer artwork, logo or branding is included.

## License

MIT — see [LICENSE](LICENSE).
