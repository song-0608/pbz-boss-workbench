# PBZ Boss Control Workbench

This repository contains the Lua mod, the Windows companion workbench, the
offline research and evidence tools, tests, and Chinese project documentation
for the verified local Phantom Blade Zero build.

## Current status

Version `ahua-boss-workbench-v1-f0bcf1323e641e03` is released, installed, enabled, and verified in the supported
local offline setup. Bride Ahua has 28 abilities and 29 bindings; WanJun has
four independent abilities and four bindings. Other Boss entries remain
locked previews.

All 79 offline check groups and current-source gameplay gates passed:
ability natural completion and active cancellation with full restoration,
600-second stability for both Bosses, ordinary workbench roundtrip, native
menu world reassembly, real target death and lock cleanup, and guarded reentry
after target collection. Formal files and host configuration remained unchanged.

Start with `开始Boss工作台.cmd`. Controls and acceptance details are in
[the delivery note](65-双Boss工作台v1交付说明.md) and
[the player guide](64-双Boss工作台操作说明.md).

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
