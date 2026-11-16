# PBZ Boss Control Workbench

This repository contains the Lua mod, the Windows companion workbench, the
offline research and evidence tools, tests, and Chinese project documentation
for the verified local Phantom Blade Zero build.

## Current status

Version `ahua-boss-workbench-v3-f7034432a74d819b` is released, installed, and
enabled for the supported local offline setup. Bride Ahua has 28 abilities and
29 bindings; WanJun, YanQianSui, and YouLong each have four independent abilities
and four bindings: **four playable Bosses, 40 abilities, 41 bindings**, with no
locked previews.

All 12 four-Boss offline check groups passed. The publisher verified the inherited
79 baseline groups, 13 three-Boss release groups, and source-matched skill and
stability evidence. Session `20261116-173808` completed eight integration checks
in the open area at Beiqi Valley's axe-Boss checkpoint: workbench restoration,
selection and cleanup, historical skill revalidation, movement and camera,
return to Ahua, pre-travel skill, native title/continue with a new World and real
skill damage, and final return to Ahua. The closed-session collector and publisher
independently passed. Formal files and host configuration remained unchanged.
Historical evidence is reused only for unchanged behavior; this does not claim
all old tests were repeated in the latest game session.

Start with `开始Boss工作台.cmd`. Controls and acceptance details are in
[the v3 delivery and player guide](70-四Boss工作台v3操作说明.md).
The external launcher starts Ahua or WanJun; select YanQianSui or YouLong through
`Insert` inside the game. YanQianSui requires open terrain; failed clearance
preserves the current Boss. Historical releases and failed attempts are retained.

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
