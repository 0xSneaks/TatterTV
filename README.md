# TatterTV 🥔📺

**Your TV, minus the remote hunt.**

TatterTV is a friendly little command-line buddy that plays what you *actually* asked for on your TV — and then checks that it really happened. No D-pad gymnastics, no "it says playing, trust me," no wrong show photobombing your movie night.

Born on a real Fire TV, during a real documentary night that went sideways in the most educational way possible. It now speaks to the whole Android TV family — and it's learning Roku next.

## The night TatterTV learned its manners

The plan was simple: put on a brand-new Mike Tyson documentary on Netflix.

What happened instead:

- Netflix was already open, so it politely **ignored the title link** it was sent.
- A hopeful press of "Play" started… **Squid Game**. (Great show. Not the assignment.)
- After a cold restart fixed the link, the TV reported "playing" again — this time it was just the **home-screen preview** doing a little dance.
- The human saved the night by finding the documentary himself. The robot took notes.

Those notes became rules, and the rules became this tool:

- **Cold-start first.** A warm app can ignore a deep link, so TatterTV restarts the app before sending it anywhere important.
- **Playing ≠ your show.** TatterTV reads back what the device itself confirms — real metadata where the device shares it (YouTube does), and an honest "the device won't tell me" where it doesn't (Netflix doesn't).
- **Find the TV, don't memorize it.** TV IP addresses are DHCP and wander off. TatterTV discovers your TV by its MAC address, every time.
- **Volume you can prove.** Turn it up, read the level back, report the actual change.

## What it does

```sh
python3 tattertv.py status                       # who's awake, what's focused, what's playing
python3 tattertv.py youtube dQw4w9WgXcQ          # play a video — title verified from metadata
python3 tattertv.py youtube <url> --expect lofi  # ...and warn me if something else shows up
python3 tattertv.py netflix 80057281             # open a Netflix title page the reliable way
python3 tattertv.py volume +2                    # louder — confirmed by the TV's own level readout
python3 tattertv.py wake                         # rise and shine
python3 tattertv.py sleep                        # and… scene. 🌙
python3 tattertv.py pause                        # snack break
python3 tattertv.py resume                       # and we're back
python3 tattertv.py key 23                       # a single honest Select
python3 tattertv.py --device "Bedroom TV" status # multi-TV households welcome
```

## Works with

- **Fire TV** — the original test couch. Battle-tested, documentary-approved.
- **Android TV / Google TV** — Sony, TCL, Hisense, Chromecast, Shield… same ADB heart, same tricks.
- **Roku** — driver built on its cheerful little HTTP API (ECP) and protocol-tested against a stand-in Roku. Lend it a real one and it'll finish its checkup.
- **Apple TV** — on the wish list, right after Roku.

## Set it up (two minutes, tops)

1. Turn on ADB debugging on the TV.
   - Fire TV: *Settings → My Fire TV → Developer Options → ADB Debugging*
   - Android/Google TV: enable Developer Options, then *Network debugging*
2. The first time TatterTV connects, your TV will ask if that's okay. It is. Tap **Allow**.
3. Copy the example config and make it yours:

```sh
cp devices.example.json devices.json
```

Your TV's MAC address lives in its network settings. `devices.json` is git-ignored on purpose — your real device details stay home, where they belong.

## The honesty bit (our favorite feature)

Most TV tools tell you what they *sent*. TatterTV tells you what the TV *said back*:

- Playback claims come from the device's media session — never from wishful thinking.
- Volume claims come from before/after level readings.
- And when a device simply can't confirm something — Netflix publishes no title metadata, full stop — TatterTV says so out loud instead of guessing with confidence.

Curious how each rule earned its place? The full story is in [docs/DESIGN.md](docs/DESIGN.md) — a small museum of everything that went wrong first, lovingly labeled.

## Pull up a couch cushion

Issues, ideas, and "it worked on my TV!" reports are all welcome. If TatterTV saves one movie night from starting the wrong show, it has done its job. 🛋️
