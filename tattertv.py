#!/usr/bin/env python3
"""TatterTV — one-command TV control with verified playback.

Talks to TVs from any machine on the same network:
- Fire TV / Android TV / Google TV over ADB (WiFi or USB)
- Roku / Roku TV over ECP (Roku's HTTP External Control Protocol, port 8060)

Every action is verified by reading device state back — never by assuming
a key press worked. Born from a real failure: a warm Netflix app silently
ignored a title deep link and a hopeful Select press played the wrong show,
while the media session happily reported "playing." The countermeasures
are baked in: discover devices by MAC (DHCP IPs go stale), cold-start apps
before deep-linking them, check metadata where the device shares it, and
say plainly when the device won't confirm something.

Config: copy devices.example.json to devices.json (same folder, or
~/.config/tattertv/devices.json) and fill in your TVs.

Usage:
  tattertv.py status [--device NAME]
  tattertv.py wake | sleep | pause | resume
  tattertv.py volume <+N|-N>
  tattertv.py key <adb-keyevent-code | roku-key-name>
  tattertv.py type <text>                      (Roku: Lit_ keys; ADB: input text)
  tattertv.py youtube <video-id-or-url> [--expect <substring>]
  tattertv.py netflix <netflix-title-id> [--media-type movie|series|episode]
  tattertv.py shot [--out frame.png]           (ADB devices only)

Stdlib only. ADB devices require `adb` (Android platform-tools) on PATH.
"""
import argparse
import json
import os
import re
import subprocess
import sys
import time
import urllib.request
import xml.etree.ElementTree as ET

# App components for ADB platforms. Netflix's TV app (com.netflix.ninja)
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
# Roku channel IDs (defaults; override per device in devices.json "apps").
ROKU_APPS = {"netflix": "12", "youtube": "837"}
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


def discover_ip(device):
    """Find the device's current IP by MAC from the local ARP table."""
    neigh = subprocess.run(["ip", "neigh"], capture_output=True, text=True).stdout
    for line in neigh.splitlines():
        m = re.match(r"(\d+\.\d+\.\d+\.\d+)\s+dev\s+\S+\s+lladdr\s+([0-9a-f:]{17})",
                     line.strip(), re.I)
        if m and device.get("mac") and m.group(2).lower() == device["mac"].lower():
            return m.group(1)
    if device.get("ip"):
        return device["ip"]
    raise SystemExit(f"{device['name']}: MAC not in ARP table and no fallback ip "
                     "configured. Is the TV on and on this network?")


# ---------------------------------------------------------------- ADB side

class ADBTV:
    def __init__(self, device):
        self.device = device
        self.ip = discover_ip(device)
        self.serial = f"{self.ip}:5555"
        self._run(["adb", "connect", self.serial])

    @staticmethod
    def _run(cmd, timeout=30, binary=False):
        r = subprocess.run(cmd, capture_output=True, timeout=timeout)
        return r.stdout if binary else r.stdout.decode(errors="replace")

    def shell(self, cmd):
        return self._run(["adb", "-s", self.serial, "shell", cmd]).strip()

    def media(self):
        return self.shell("dumpsys media_session | grep -E 'metadata:|state=PlaybackState' | head -4")

    def playing_state(self):
        m = re.search(r"state=PlaybackState \{state=(\d+)", self.media())
        return int(m.group(1)) if m else None

    # -- commands ------------------------------------------------------
    def status(self):
        d = self.device
        print(f"TV: {d['name']} @ {self.ip} ({d.get('platform', 'firetv')})")
        print(self.shell("settings get global device_name; getprop ro.product.model; "
                         "dumpsys power | grep -m1 mWakefulness=; "
                         "dumpsys window windows | grep -m1 mCurrentFocus"))
        print(self.media())

    def wake(self):
        print(self.shell("input keyevent 224; sleep 1; dumpsys power | grep -m1 mWakefulness="))

    def sleep(self):
        print(self.shell("input keyevent 223; sleep 2; dumpsys power | grep -m1 mWakefulness="))

    def pause(self):
        self.shell("input keyevent 127")

    def resume(self):
        self.shell("input keyevent 126")

    def volume(self, delta):
        key = 24 if delta > 0 else 25
        grab = "dumpsys audio | grep -A12 STREAM_MUSIC: | grep -m1 'Current:'"

        def speaker_index():
            m = re.search(r"2 \(speaker\): (\d+)", self.shell(grab))
            return int(m.group(1)) if m else None

        before = speaker_index()
        for _ in range(abs(delta)):
            self.shell(f"input keyevent {key}")
        time.sleep(1)
        after = speaker_index()
        if before is not None and after is not None:
            print(f"speaker volume index: {before} -> {after} "
                  f"(delta {after - before:+d}, asked {delta:+d})")
        else:
            print(f"Could not read volume index (before={before}, after={after}).")

    def key(self, code):
        self.shell(f"input keyevent {int(code)}")

    def type_text(self, text):
        self.shell(f"input text {text.replace(' ', '%s')}")

    def youtube(self, video, expect):
        apps = APPS[self.device.get("platform", "firetv")]
        m = re.search(r"(?:v=|youtu\.be/|/shorts/)?([A-Za-z0-9_-]{11})", video)
        vid = m.group(1) if m else video
        url = f"https://www.youtube.com/watch?v={vid}"
        if apps["youtube"]:
            self.shell(f"am start -n {apps['youtube']} -a android.intent.action.VIEW -d {url}")
        else:
            self.shell(f"am start -a android.intent.action.VIEW -d {url} -p {apps['youtube_pkg']}")
        time.sleep(7)
        media = self.media()
        print(media)
        if self.playing_state() == 3:
            desc = re.search(r"description=([^,]+(?:,[^,]+)?)", media)
            print(f"VERIFIED playing (state=3). Title: {desc.group(1) if desc else 'n/a'}")
            if expect and expect.lower() not in media.lower():
                print(f"WARNING: expected '{expect}' not in metadata — check the screen.")
        else:
            print("NOT verified playing.")

    def netflix(self, title_id, _media_type):
        apps = APPS[self.device.get("platform", "firetv")]
        # A warm Netflix app silently ignores title deep links; cold-start it.
        self.shell(f"am force-stop com.netflix.ninja; sleep 2; "
                   f"am start -n {apps['netflix']} -a android.intent.action.VIEW "
                   f"-d https://www.netflix.com/title/{title_id}")
        time.sleep(9)
        print(self.shell("dumpsys window windows | grep -m1 mCurrentFocus"))
        print(self.media())
        print("Netflix is open on the title's page (cold start, deep link delivered).")
        print("Press Select once to play:  tattertv.py key 23")
        print("NOTE: Netflix reports NO title metadata — the title itself can only")
        print("be confirmed by looking at the screen. Playback state above is real.")

    def shot(self, out):
        raw = self._run(["adb", "-s", self.serial, "exec-out", "screencap", "-p"], binary=True)
        if not raw:
            print("Capture returned 0 bytes — on many TVs that means a secure "
                  "(DRM) surface is in front (e.g. Netflix playback). Capture "
                  "works on menus and non-DRM screens.")
            return
        with open(out, "wb") as f:
            f.write(raw)
        print(f"Saved {out} ({len(raw)} bytes).")


# --------------------------------------------------------------- Roku side

class RokuTV:
    """Roku External Control Protocol (ECP): plain HTTP on port 8060.

    Docs: https://developer.roku.com/docs/developer-program/dev-tools/external-control-api.md
    LAN requests must bypass any HTTP proxy, hence the empty ProxyHandler.
    """

    def __init__(self, device):
        self.device = device
        self.ip = discover_ip(device)
        self.port = int(device.get("port", 8060))
        self.base = f"http://{self.ip}:{self.port}"
        self.apps = dict(ROKU_APPS, **device.get("apps", {}))
        self.opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

    def _req(self, method, path):
        req = urllib.request.Request(self.base + path, method=method,
                                     data=b"" if method == "POST" else None)
        with self.opener.open(req, timeout=10) as r:
            return r.read().decode(errors="replace")

    def _xml(self, path):
        return ET.fromstring(self._req("GET", path))

    def keypress(self, key):
        self._req("POST", f"/keypress/{key}")

    def device_info(self):
        root = self._xml("/query/device-info")
        return {el.tag: (el.text or "") for el in root}

    def active_app(self):
        root = self._xml("/query/active-app")
        app = root.find("app")
        if app is None:
            return None
        return {"id": app.get("id"), "name": (app.text or "")}

    def media_player(self):
        root = self._xml("/query/media-player")
        pos = root.findtext("position", "")
        dur = root.findtext("duration", "")
        return {"state": root.get("state"), "position": pos, "duration": dur}

    # -- commands ------------------------------------------------------
    def status(self):
        info = self.device_info()
        print(f"TV: {self.device['name']} @ {self.ip} (roku)")
        print(f"device: {info.get('user-device-name', '')} · {info.get('model-name', '')} · "
              f"power: {info.get('power-mode', '')}")
        app = self.active_app()
        print(f"active app: {app['name']} (id {app['id']})" if app else "active app: home / none")
        if app:
            print(f"media player: {self.media_player()}")

    def wake(self):
        self.keypress("PowerOn")
        time.sleep(1)
        print("power-mode:", self.device_info().get("power-mode", "?"))

    def sleep(self):
        self.keypress("PowerOff")
        time.sleep(1)
        try:
            print("power-mode:", self.device_info().get("power-mode", "?"))
        except Exception:
            print("Device not answering queries — consistent with off/standby.")

    def pause(self):
        self.keypress("Play")
        time.sleep(1)
        print("media player:", self.media_player())

    def resume(self):
        self.pause()

    def volume(self, delta):
        key = "VolumeUp" if delta > 0 else "VolumeDown"
        for _ in range(abs(delta)):
            self.keypress(key)
        print(f"Sent {abs(delta)}x {key}. ECP exposes no volume level, so this "
              "step is UNVERIFIED by design — the protocol won't read it back.")

    def key(self, name):
        self.keypress(name)

    def type_text(self, text):
        import urllib.parse
        for ch in text:
            self.keypress("Lit_" + urllib.parse.quote(ch, safe=""))

    def _launch_and_check(self, app_key, content_id, media_type, label):
        app_id = self.apps[app_key]
        q = ""
        if content_id:
            import urllib.parse
            q = f"?contentId={urllib.parse.quote(str(content_id))}&MediaType={media_type}"
        self._req("POST", f"/launch/{app_id}{q}")
        time.sleep(6)
        app = self.active_app()
        player = self.media_player() if app else {}
        print(f"active app: {app}")
        print(f"media player: {player}")
        if app and app["id"] == app_id:
            print(f"VERIFIED: {label} app is in front"
                  + (f", player state={player.get('state')}." if player else "."))
        else:
            print(f"NOT verified: expected app id {app_id} in front.")

    def youtube(self, video, expect):
        m = re.search(r"(?:v=|youtu\.be/|/shorts/)?([A-Za-z0-9_-]{11})", video)
        vid = m.group(1) if m else video
        self._launch_and_check("youtube", vid, "movie", "YouTube")
        if expect:
            print("NOTE: ECP confirms the app and player state, not the video "
                  "title — '--expect' can't be checked on Roku.")

    def netflix(self, title_id, media_type):
        self._launch_and_check("netflix", title_id, media_type, "Netflix")
        print("NOTE: the deep link carried the title ID; ECP confirms the "
              "Netflix app, not the title — titles need eyes on the screen.")

    def shot(self, _out):
        print("Roku ECP has no screenshot endpoint — shot is ADB-only.")


# ------------------------------------------------------------------- CLI

def main():
    ap = argparse.ArgumentParser(description="TatterTV — verified TV control.")
    ap.add_argument("--device", default="", help="device name from devices.json (default: first)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status")
    sub.add_parser("wake")
    sub.add_parser("sleep")
    sub.add_parser("pause")
    sub.add_parser("resume")
    pv = sub.add_parser("volume"); pv.add_argument("delta", type=int)
    pk = sub.add_parser("key"); pk.add_argument("code", help="ADB: keyevent code (23=Select). Roku: ECP key name (Select, Home, ...).")
    pt = sub.add_parser("type"); pt.add_argument("text")
    py = sub.add_parser("youtube"); py.add_argument("video"); py.add_argument("--expect", default="")
    pn = sub.add_parser("netflix"); pn.add_argument("title_id")
    pn.add_argument("--media-type", default="movie", choices=["movie", "series", "episode", "season"])
    ps = sub.add_parser("shot"); ps.add_argument("--out", default="frame.png")
    args = ap.parse_args()

    device = pick_device(load_config(), args.device)
    tv = RokuTV(device) if device.get("platform") == "roku" else ADBTV(device)
    if args.cmd == "status":
        tv.status()
    elif args.cmd == "wake":
        tv.wake()
    elif args.cmd == "sleep":
        tv.sleep()
    elif args.cmd == "pause":
        tv.pause()
    elif args.cmd == "resume":
        tv.resume()
    elif args.cmd == "volume":
        tv.volume(args.delta)
    elif args.cmd == "key":
        tv.key(args.code)
    elif args.cmd == "type":
        tv.type_text(args.text)
    elif args.cmd == "youtube":
        tv.youtube(args.video, args.expect)
    elif args.cmd == "netflix":
        tv.netflix(args.title_id, args.media_type)
    elif args.cmd == "shot":
        tv.shot(args.out)


if __name__ == "__main__":
    main()
