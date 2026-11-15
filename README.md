# PBZ Boss Control Workbench

This repository contains the Lua mod, the Windows companion workbench, the
offline research and evidence tools, tests, and Chinese project documentation
for the verified local Phantom Blade Zero build.

## Current status

The working tree is archived as an acceptance candidate, not a complete public
release. The in-game companion overlay can select Bride Ahua or WanJun. Other
Boss entries remain locked previews until their identity and combat lifecycle
are verified. Current-source acceptance and supported machine setup are
documented in [63-整体优化与工作台收尾.md](63-整体优化与工作台收尾.md) and
[64-双Boss工作台操作说明.md](64-双Boss工作台操作说明.md).

The frozen candidate is `ahua-28-m2-3524e745dc21da3c`. Its workbench interaction,
ordinary Ahua/WanJun/Ahua roundtrip, and same-process native menu world cycle
passed in closed session `20261116-031001`. These checks include owned-object
cleanup, movement, camera control, character-specific skills, automatic world
reassembly, ordinary skill damage, and full player restoration.

The candidate skips expired or dead initial targets, retains camera restoration
records before target handling, and gives each newly loaded player its full
stability-observation window. Current-source ability, continuous-takeover,
independent WanJun baseline, and dead-target recovery acceptance are being
completed. Earlier candidates' gameplay results remain historical evidence.
All 79 offline check groups passed on 2026-11-16; this does not replace gameplay
acceptance.

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
