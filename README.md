# TatterTV

One-command TV control over ADB — with **verified** playback, not hopeful key presses.

Works with Fire TV, Android TV, and Google TV devices from any machine on the same network. Stdlib-only Python; the only requirement is `adb` (Android platform-tools) on your PATH.

## Why

TV apps lie by omission:

- A media session reporting "playing" doesn't say *what* is playing — a home-screen preview counts.
- A warm Netflix app silently ignores title deep links, so a follow-up "Play" press starts whatever happened to have focus.
- TV IPs are DHCP leases; hard-coding one works until it doesn't.

TatterTV encodes the countermeasures: discover devices by MAC address, cold-start an app before deep-linking into it, verify volume by the device's own level readout, and say plainly when the device won't confirm something (Netflix reports no title metadata — the tool tells you that instead of pretending).

## Setup

1. Enable ADB debugging on the TV (Fire TV: Settings → My Fire TV → Developer Options → ADB Debugging; Android/Google TV: enable Developer Options, then Network debugging).
2. Accept the debugging prompt on the TV the first time you connect.
3. Copy the config template and fill in your TVs:

```sh
cp devices.example.json devices.json
```

Find a TV's MAC in its network settings. `devices.json` is git-ignored — real device details never belong in the repo.

## Commands

```sh
python3 tattertv.py status                      # device, power, focused app, media state + metadata
python3 tattertv.py wake                        # wake and read back power state
python3 tattertv.py sleep                       # sleep and read back power state
python3 tattertv.py youtube dQw4w9WgXcQ         # play a video, verify title from metadata
python3 tattertv.py youtube <url> --expect "lofi"   # warn if a different title is playing
python3 tattertv.py netflix 80057281            # open a Netflix title page (cold start)
python3 tattertv.py volume +2                   # verified by level readback
python3 tattertv.py pause | resume
python3 tattertv.py key 23                      # raw keyevent (23 = Select)
python3 tattertv.py --device "Bedroom TV" status
```

## Platform notes

- **Fire TV** — battle-tested path. YouTube and Netflix launch by pinned component.
- **Android TV / Google TV** — same ADB core; YouTube launches by package. Netflix uses the same TV app package as Fire TV.
- **Roku / Apple TV** — different protocols (Roku: HTTP ECP; Apple TV: pyatv). Not yet implemented; the command surface is designed to take them as additional drivers.

## Honesty rules built in

- Playback claims come from `dumpsys media_session` readbacks, never from the fact a command was sent.
- Volume claims come from the device's reported level before/after.
- Netflix title verification from the device is impossible today (no metadata is published); `netflix` reports state and tells you the title needs eyes on the screen.

See [docs/DESIGN.md](docs/DESIGN.md) for the failure catalogue that produced these rules.
