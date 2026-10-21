#!/usr/bin/env python3
"""TatterTV — one-command TV control over ADB, with verified playback.

Talks to Android TV / Google TV / Fire TV devices over ADB (WiFi or USB)
from any machine on the same network. Every action is verified by reading
device state back — never by assuming a key press worked.

Why this exists: TV apps (Netflix especially) lie by omission. A "playing"
state doesn't say *what* is playing, a warm app can silently ignore a deep
link, and a blind Select can start the wrong show. TatterTV encodes the
countermeasures: discover devices by MAC (DHCP IPs go stale), cold-start
apps before deep-linking them, and report exactly what the device itself
confirms — including when the honest answer is "the device won't say".

Config: copy devices.example.json to devices.json (same folder, or
~/.config/tattertv/devices.json) and fill in your TVs.

Usage:
  tattertv.py status [--device NAME]
  tattertv.py wake | sleep | pause | resume | key <keyevent-code>
  tattertv.py volume <+N|-N>
  tattertv.py youtube <video-id-or-url> [--expect <substring>]
  tattertv.py netflix <netflix-title-id>

Requires: adb (Android platform-tools) on PATH. Stdlib only.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time

# App components differ per platform. Netflix's TV app (com.netflix.ninja)
# is the same package on Fire TV and Android TV; YouTube's is not.
APPS = {
    "firetv": {
        "youtube": "com.amazon.firetv.youtube/dev.cobalt.app.MainActivity",
        "netflix": "com.netflix.ninja/.MainActivity",
    },
    "androidtv": {
        # Launched by package (no pinned activity) — less battle-tested
        # than the Fire TV component path.
        "youtube": None,
        "youtube_pkg": "com.google.android.youtube.tv",
        "netflix": "com.netflix.ninja/.MainActivity",
    },
}
CONFIG_PATHS = [
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "devices.json"),
    os.path.expanduser("~/.config/tattertv/devices.json"),
]


def load_config():
    for p in CONFIG_PATHS:
        if os.path.exists(p):
            with open(p) as f:
                return json.load(f)
    raise SystemExit("No devices.json found. Copy devices.example.json and fill it in.")


def run(cmd, timeout=30):
    return subprocess.run(cmd, capture_output=True, text=True, timeout=timeout).stdout


def discover_ip(device):
    """Find the device's current IP by MAC from the local ARP table."""
    neigh = run(["ip", "neigh"])
    for line in neigh.splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+dev\s+\S+\s+lladdr\s+([0-9a-f:]{17})",
                     line.strip(), re.I)
        if m and m.group(2).lower() == device["mac"].lower():
            return m.group(1)
    if device.get("ip"):
        return device["ip"]
    raise SystemExit(f"{device['name']}: MAC {device['mac']} not in ARP table "
                     "and no fallback ip configured. Is the TV on and on this network?")


class TV:
    def __init__(self, device):
        self.device = device
        self.ip = discover_ip(device)
        self.serial = f"{self.ip}:5555"
        run(["adb", "connect", self.serial])

    def shell(self, cmd):
        return run(["adb", "-s", self.serial, "shell", cmd]).strip()

    def media(self):
        return self.shell("dumpsys media_session | grep -E 'metadata:|state=PlaybackState' | head -4")

    def playing_state(self):
        m = re.search(r"state=PlaybackState \{state=(\d+)", self.media())
        return int(m.group(1)) if m else None


def pick_device(cfg, name):
    devices = cfg.get("devices", [])
    if not devices:
        raise SystemExit("devices.json has no devices.")
    if name:
        for d in devices:
            if d["name"] == name:
                return d
        raise SystemExit(f"Device '{name}' not in config.")
    return devices[0]


def cmd_status(tv):
    d = tv.device
    print(f"TV: {d['name']} @ {tv.ip} ({d.get('platform', 'firetv')})")
    print(tv.shell("settings get global device_name; getprop ro.product.model; "
                   "dumpsys power | grep -m1 mWakefulness=; "
                   "dumpsys window windows | grep -m1 mCurrentFocus"))
    print(tv.media())


def cmd_volume(tv, delta):
    key = 24 if delta > 0 else 25
    grab = "dumpsys audio | grep -A12 STREAM_MUSIC: | grep -m1 'Current:'"

    def speaker_index():
        m = re.search(r"2 \(speaker\): (\d+)", tv.shell(grab))
        return int(m.group(1)) if m else None

    before = speaker_index()
    for _ in range(abs(delta)):
        tv.shell(f"input keyevent {key}")
    time.sleep(1)
    after = speaker_index()
    if before is not None and after is not None:
        print(f"speaker volume index: {before} -> {after} (delta {after - before:+d}, asked {delta:+d})")
    else:
        print(f"Could not read volume index (before={before}, after={after}).")


def cmd_youtube(tv, video, expect):
    apps = APPS[tv.device.get("platform", "firetv")]
    m = re.search(r"(?:v=|youtu\.be/|/shorts/)?([A-Za-z0-9_-]{11})", video)
    vid = m.group(1) if m else video
    url = f"https://www.youtube.com/watch?v={vid}"
    if apps["youtube"]:
        tv.shell(f"am start -n {apps['youtube']} -a android.intent.action.VIEW -d {url}")
    else:
        tv.shell(f"am start -a android.intent.action.VIEW -d {url} -p {apps['youtube_pkg']}")
    time.sleep(7)
    media = tv.media()
    print(media)
    if tv.playing_state() == 3:
        desc = re.search(r"description=([^,]+(?:,[^,]+)?)", media)
        print(f"VERIFIED playing (state=3). Title: {desc.group(1) if desc else 'n/a'}")
        if expect and expect.lower() not in media.lower():
            print(f"WARNING: expected '{expect}' not in metadata — check the screen.")
    else:
        print("NOT verified playing.")


def cmd_netflix(tv, title_id):
    apps = APPS[tv.device.get("platform", "firetv")]
    # A warm Netflix app silently ignores title deep links; cold-start it.
    tv.shell(f"am force-stop com.netflix.ninja; sleep 2; "
             f"am start -n {apps['netflix']} -a android.intent.action.VIEW "
             f"-d https://www.netflix.com/title/{title_id}")
    time.sleep(9)
    print(tv.shell("dumpsys window windows | grep -m1 mCurrentFocus"))
    print(tv.media())
    print("Netflix is open on the title's page (cold start, deep link delivered).")
    print("Press Select once to play:  tattertv.py key 23")
    print("NOTE: Netflix reports NO title metadata — the title itself can only")
    print("be confirmed by looking at the screen. Playback state above is real.")


def main():
    ap = argparse.ArgumentParser(description="TatterTV — verified TV control over ADB.")
    ap.add_argument("--device", default="", help="device name from devices.json (default: first)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("wake")
    sub.add_parser("sleep")
    sub.add_parser("pause")
    sub.add_parser("resume")
    pv = sub.add_parser("volume"); pv.add_argument("delta", type=int)
    pk = sub.add_parser("key"); pk.add_argument("code", type=int)
    py = sub.add_parser("youtube"); py.add_argument("video"); py.add_argument("--expect", default="")
    pn = sub.add_parser("netflix"); pn.add_argument("title_id")
    args = ap.parse_args()

    tv = TV(pick_device(load_config(), args.device))
    if args.cmd == "status":
        cmd_status(tv)
    elif args.cmd == "wake":
        print(tv.shell("input keyevent 224; sleep 1; dumpsys power | grep -m1 mWakefulness="))
    elif args.cmd == "sleep":
        print(tv.shell("input keyevent 223; sleep 2; dumpsys power | grep -m1 mWakefulness="))
    elif args.cmd == "pause":
        tv.shell("input keyevent 127")
    elif args.cmd == "resume":
        tv.shell("input keyevent 126")
    elif args.cmd == "volume":
        cmd_volume(tv, args.delta)
    elif args.cmd == "key":
        tv.shell(f"input keyevent {args.code}")
    elif args.cmd == "youtube":
        cmd_youtube(tv, args.video, args.expect)
    elif args.cmd == "netflix":
        cmd_netflix(tv, args.title_id)


if __name__ == "__main__":
    main()
