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

The WanJun candidate passed its four ability natural-completion and active
cancellation checks, movement and camera checks, a 600-second assembly, more
than eight minutes of continuous takeover, and clean isolated-session
restoration on 2026-11-15. Current-source workbench interaction and the ordinary
Ahua/WanJun/Ahua roundtrip passed in closed session `20261115-232001`, including
owned-object cleanup, movement, camera control, and character-specific skills.
The same-process native menu world cycle passed in closed session
`20261116-005016`: automatic reassembly, ordinary skill damage, and full player
restoration. The previous frozen candidate completed all 28 Ahua natural and
active-cancellation checks and 29 bindings. A later dead-target reentry test
found a reference to a collected training actor in setup observation. The new
candidate skips expired or dead initial targets and retains camera restoration
records before target handling; current-source gameplay revalidation is pending.
All 79 offline check
groups passed on 2026-11-16; this does not replace gameplay acceptance.

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
