# PBZ Boss Control Workbench

This repository contains the Lua mod, the Windows companion workbench, the
offline research and evidence tools, tests, and Chinese project documentation
for the verified local Phantom Blade Zero build.

## Current status

Version `ahua-boss-workbench-v2-7b83ce4aa5d15a03` is released for the supported
local offline setup. Bride Ahua has 28 abilities and 29 bindings; WanJun and
YouLong each have four independent abilities and four bindings: **three playable
Bosses, 36 abilities, 37 bindings**. YanQianSui remains a locked preview because
terrain, movement/camera, and world integration acceptance is incomplete.

All 79 baseline offline check groups were rerun on current sources, with 13
additional release checks. Ahua and WanJun inherit their immutable v1 acceptance;
every common runtime change is reconstructed from that base and limited to
initialization, selection preflight, and catalogs. YouLong has an independently
accepted 600-second baseline, eight ordinary natural/cancellation actions, and
a fresh exact-three-profile native menu/world cycle on November 16, 2026.
New-world damage, full player restoration, and return to Ahua passed. Formal
files and host configuration remained unchanged. Historical evidence is reused
only for unchanged behavior; this does not claim all old tests were repeated
in the latest game session.

Start with `开始Boss工作台.cmd`. Controls and acceptance details are in
[the v2 delivery and player guide](67-三Boss工作台v2交付说明.md).
The external launcher starts Ahua or WanJun; select YouLong through `Insert`
inside the game. The immutable v1 package remains available for rollback.

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
