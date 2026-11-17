# PBZ Boss Control Workbench

This repository contains the Lua mod, the Windows companion workbench, the
offline research and evidence tools, tests, and Chinese project documentation
for the verified local Phantom Blade Zero build.

## Current status

Version `ahua-boss-workbench-v4-d2cb2593f6ea392e` is released, installed, and
enabled for the supported local offline setup. Bride Ahua has 28 abilities and
29 bindings; WanJun, YanQianSui, and YouLong each have eight independent abilities
and eight bindings: **four playable Bosses, 52 abilities, 53 bindings**, with no
locked previews.

All 13 v4 offline check groups passed. The publisher independently replayed the
12 new skill receipts, including natural completion and cancellation. Ordinary
session `20261117-152918` passed 24 new actions, Boss selection, movement and
camera, and return to Ahua. Separate session `20261117-155229` passed native
title/continue, new-World assembly, cleanup, real skill damage and restoration.
The closed-session collectors and publisher passed; these are separate sessions.
Unchanged execution, camera, input and restoration inherit the accepted v3
baseline. This does not claim all historical tests were repeated.

Start with `开始Boss工作台.cmd`. Controls and acceptance details are in
[the v4 delivery and player guide](72-四Boss技能扩展v4操作说明.md).
The external launcher starts Ahua or WanJun; select YanQianSui or YouLong through
`Insert` inside the game. YanQianSui requires open terrain; failed clearance
preserves the current Boss. Historical releases and failed attempts are retained.

The research environment and a fixed Beiqi Valley axe-Boss save snapshot live
under `E:\项目\PBZ-Boss操控研究`; source remains on D:. Workbench preparation
automatically applies the hash-checked scene snapshot and backs up the previous
research progress. The subsequent cold-start visual confirmation was interrupted
by a window-tool error and is not marked verified. Formal saves are unchanged.
Network adaptation remains deferred.

## Performance

The severe stutter reported after F6 was traced to the diagnostic launcher
disabling the native UObject array cache. The performance profile restores
that cache and uses incremental status reads and input dispatch. Historical
callback timing improved from about 365 ms to about 2.5 ms; this measures the
game-thread callback, not GPU frame rate. Details and caveats are recorded in
the project acceptance documents.

## Workbench controls

- `Insert`: open or close Boss selection
- `Up` / `Down`: select an entry
- `Enter`: confirm a verified Boss configuration
- `Esc` / `F10`: close the workbench or restore the original player
- `F6`: take over the selected Boss after setup settles

The selector is a keyboard-controlled Windows companion overlay over the game
window, not a native Unreal UMG or mouse-driven menu. The research launcher
uses an isolated, offline local setup and is not a portable installer for
arbitrary machines. Do not install it into the formal game directory or copy
research progress into a formal save.

## Archive scope

Source, tests, curated acceptance summaries, and documentation are tracked.
Game executables and assets, save files, sandbox images, dependency downloads,
live session state, raw machine logs, and machine-specific credentials are
excluded. Rebuild and acceptance prerequisites are local and documented in
the research workflow.
