# Design notes — the failure catalogue

TatterTV was designed backwards from real failures controlling a TV
headlessly. Each rule in the code answers a specific incident.

## Failures that shaped the design

1. **Wrong show, confidently reported.** A title deep link was sent to a
   Netflix app that was already running. The app ignored the link; a
   follow-up Select press played whatever had focus, and the media session
   happily reported "playing." It was the wrong show.
   → *Cold-start apps before deep-linking. Never treat "playing" as
   proof of what is playing.*

2. **The home-screen preview that looked like success.** After a correct
   cold start, the media session again reported "playing" — the home
   billboard preview autoplaying, not the title.
   → *Playback state is evidence about the player, not the title. Where
   metadata exists (YouTube), check it. Where it doesn't (Netflix), say so.*

3. **The stale IP.** The TV's DHCP address stopped answering mid-task and
   every command failed against a silent host.
   → *Discover by MAC from the ARP table on every run; keep IPs as
   fallbacks only.*

4. **The invisible UI.** `uiautomator dump` inside Netflix returns an
   empty tree — the app renders outside the accessibility hierarchy.
   Menu navigation by feel (Up/Left/Select guesses) landed on the profile
   screen.
   → *No blind multi-key navigation sequences. One verified step at a
   time, or a deep link.*

5. **Timeouts that ate the evidence.** Long batched remote commands hit a
   transport timeout and returned nothing at all, including the parts that
   had succeeded.
   → *Keep each remote operation short; verify after, in a separate call.*

## What cannot be fixed from the controller side

- **Netflix title readback.** The app publishes no title metadata to the
  media session and exposes no readable UI tree. Any tool claiming to
  verify a Netflix title from the device alone is guessing.
- **The transport is only as alive as its host.** If the relay/bridge
  hosting ADB access goes down, the controller can retry and report, not
  resurrect it.

## Roadmap

- **Screenshot verification.** Capture the TV screen (`screencap`), pull
  it back, and check the actual frame before acting at decision points.
  This closes the Netflix blindness: a title page is readable in pixels
  even when it is invisible to the accessibility tree.
- **Roku driver** (HTTP ECP: keypress + app launch + search endpoints).
- **Apple TV driver** (pyatv).
