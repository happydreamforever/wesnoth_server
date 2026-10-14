# First offline emulator milestone passed

The user confirms that the actual Android game in LDPlayer joined the Windows server, played against the computer, returned control after the AI turn and kept its connection active. Internet/WAN was disconnected while local Ethernet stayed connected. The existing APK uses the verified gamedata-1.19.26 OBB. The first offline Windows-server/LDPlayer playable baseline is complete at this tested scope.

The latest tested Windows commits are server 275f0ea and client bfa53b8. Later documentation-only commits record results and do not require another pull, rebuild, reinstall, data copy or repeated emulator turn. Keep all completed stages and the working app/server.

## Current next step: game design, LDPlayer only

The user has chosen to test only with LDPlayer. Do not request a phone, USB inspection or another ABI. The current server-connected offline AI-turn test remains complete.

Current task: explain existing guest-server storage and campaign/multiplayer progression, and present ten team-mode proposals. MongoDB integration, permanent accounts and hero progression across independent matches are not implemented. Campaign saves and within-match unit leveling already exist on the client. Read the latest BASELINE.md section for the source audit and proposals.

Before building persistent cross-mode progression, define account versus hero levels, how campaign rewards are accepted, and whether PvP uses full persistent stats, level brackets or normalized stats. No particular mode or progression policy has been selected. This is a design discussion, so no new build, pull, install or test is required. When a feature is selected, keep Windows testing one step per reply; later two-human tests can use separate LDPlayer instances.

## Saved evidence

- Windows server startup: server diagnostics/server-run-20261013-171523-854.txt. Pasted startup/idle excerpt only; later gameplay events were not supplied.
- Windows address report: server diagnostics/lan-address-20261013-195939-200-65afa4e99f034483840e206209ac0c2b.txt. wesnothd PID16216, IPv4/IPv6 port15000, Ethernet100.99.99.14/Public; metadata check passed.
- User observations: multiplayer lobby appeared, play against the computer worked, control returned after the computer turn, connection remained active, and internet/WAN was explicitly disconnected while Ethernet remained active.

The successful endpoint was 100.99.99.14:15000 for that session. Do not assume the address/PID stays fixed. The Public profile did not block the reported connection; no firewall/profile changes or guessed gateway are needed. If a later connection fails after a network change, use the existing address helper against the then-current state.
