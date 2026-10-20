# Next milestone: connect Android player accounts to Windows

The standalone Android transport check is complete. The latest device-only run passes all 22 cases, both file hashes and receipt verification. Your corrected report confirms internet/WAN was disconnected during that run. No further transport test, pull, rebuild, reinstall or database initialization is needed for this checkpoint.

## Next implementation and acceptance

The next delivery will connect the actual Android account UI to the Windows Alliance service and its existing local MongoDB. It must provide:

1. A trusted import of the Windows public connection profile; the server private key and backend bridge credential stay on Windows.
2. Versioned account messages with bounded frame/decompression sizes, timeouts and cancellation, plus an asynchronous native bridge restricted to player registration, login, profile and logout.
3. A minimal in-game account flow: create a player account with a starter leader, log in, view that same leader, and log out. A logged-out session must be rejected.

This account integration is not yet delivered. There is no new Windows command to run for it in this documentation-only checkpoint. Once its implementation and VPS verification are complete, replace this handoff with exact MSYS2 Git pull, build/run/test commands, expected results and saved-log paths. Do not substitute another loopback transport fixture for the actual Android-to-Windows account test.

Use the existing profile database at `%LOCALAPPDATA%\WesnothAlliance\runtime`, selected LDPlayer instance and verified game data/OBB. Database/admin acceptance remains valid. Keep the working guest game and all completed stages. The future account acceptance must run with WAN disconnected while retaining the local network; Android must communicate with the Windows service, not connect directly to MongoDB or the operator website. Team and campaign integration follow account acceptance.
