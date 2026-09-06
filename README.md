# Daggerwalk

![The Daggerfall logo](https://djfdm802jwooz.cloudfront.net/static/img/daggerwalk/orig_daggerfall_logo.png)

Daggerwalk is a Twitch stream of a bot endlessly walking through *The Elder Scrolls II: Daggerfall*. Chat can steer the Walker, talk to NPCs, explore dungeons, complete quests, and play through the entire game together.

[Watch on Twitch](https://www.twitch.tv/daggerwalk) · [View the map, quests, and travel log](https://www.kershner.org/daggerwalk)

This is the working repository for the Windows machine that runs the stream. It contains the Twitch bot, game automation, custom Daggerfall Unity mods, the local control page, and the scripts that start and recover the whole thing. It is built around that machine rather than packaged for general use.

## Contents

- `daggerwalk/` — Python bot and stream automation
- `mods/dfu/` — Daggerfall Unity mod sources
- `tests/` — bot and command tests
- `tools/youtube/` — unused for now, kept in case YouTube returns
- `data/` and `runtime/` — ignored local data, logs, and state

The stream is started with `start_daggerwalk.bat`. Passing `--mode dev` skips Twitch and OBS and runs the local controls instead.
