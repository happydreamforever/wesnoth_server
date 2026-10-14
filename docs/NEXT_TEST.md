# First offline emulator milestone passed

The user confirms that the actual Android game in LDPlayer joined the Windows server, played against the computer, returned control after the AI turn and kept its connection active. Internet/WAN was disconnected while local Ethernet stayed connected. The existing APK uses the verified gamedata-1.19.26 OBB. The first offline Windows-server/LDPlayer playable baseline is complete at this tested scope.

The latest tested Windows commits are server 275f0ea and client bfa53b8. Later documentation-only commits record results and do not require another pull, rebuild, reinstall, data copy or repeated emulator turn. Keep all completed stages and the working app/server.

## Immediate next step

Ask whether a physical Android phone is available to connect to Windows by USB. Keep the user's requested one-step-at-a-time pace. No new command is required for the completed emulator test.

If a phone is available, the next device step should establish USB/ADB visibility and that phone's actual Android API and ABI. The existing installed APK targets x86_64 LDPlayer; do not install it on a guessed phone ABI or select an ARM target based only on a model name. Use the already verified Windows Android SDK tools, then choose the necessary phone build from the returned device evidence.

If no phone is available, agree on the next available test or development milestone. Separate-phone connectivity, two-human synchronization, MongoDB persistence and custom game features remain untested. Do not describe the successful one-human-plus-AI session as two-device synchronization.

## Saved evidence

- Windows server startup: server diagnostics/server-run-20261013-171523-854.txt. Pasted startup/idle excerpt only; later gameplay events were not supplied.
- Windows address report: server diagnostics/lan-address-20261013-195939-200-65afa4e99f034483840e206209ac0c2b.txt. wesnothd PID16216, IPv4/IPv6 port15000, Ethernet100.99.99.14/Public; metadata check passed.
- User observations: multiplayer lobby appeared, play against the computer worked, control returned after the computer turn, connection remained active, and internet/WAN was explicitly disconnected while Ethernet remained active.

The successful endpoint was 100.99.99.14:15000 for that session. Do not assume the address/PID stays fixed. The Public profile did not block the reported connection; no firewall/profile changes or guessed gateway are needed. If a later connection fails after a network change, use the existing address helper against the then-current state.
