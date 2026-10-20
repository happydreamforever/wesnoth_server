# Next test: quit and reopen the Android game

The user confirms the exact **Logged out. The server has revoked this session.** message, then successful UniPlayer repeat login and a separate matching personal-leader view. WAN stayed disconnected while local Ethernet remained connected. Accept logout acknowledgement and repeat account access at user-observed scope. This is not a direct old-token replay or database/app restart test.

**Current step: restart only the game and verify saved profile plus fresh login.** Keep the database, admin-service and account-bridge windows running. Keep Ethernet connected and WAN disconnected. No PowerShell command, pull, build, reinstall, new account, profile import or database restart is needed. Start this test while still logged in; do not choose Log out first.

## Quit and reopen

1. Select **OK** to close the personal-leader message, then **Back to game** to return to the main menu.
2. Choose the game's actual **Quit** button. Wait for the game to close. This source path ends the native process; simply navigating away does not test that path.
3. From the LDPlayer home screen, open **Wesnoth Offline** again. If the setup screen reappears automatically after Quit, continue there.
4. Expected setup screen: **Wesnoth Alliance** still shows **Trusted server: 100.99.99.14:15001** and its saved fingerprint. Do not reimport the profile. If it is missing/invalid, stop and report the screen.
5. Choose **Start game**, wait for the main menu, then open **Alliance**. Expected: **Create player account / Log in**, without an already logged-in player. The session is kept only in process memory. If it still says Logged in as UniPlayer, stop and report that result.
6. Select **Log in → Open** and use the existing `UniPlayer` credentials. After **Logged in**, select **OK → View personal leader → Open**.
7. Expected: the same on-screen player ID, **UniPlayer**, **Spearman**, **Level 1**, **Experience 0**, **Total experience 0**.

**Stop with that profile visible.** Report whether Quit closed the game, the trusted server remained saved, Alliance required login after reopening, and the player ID/leader still matched. Confirm WAN stayed disconnected. Send any displayed error, but no passwords, tokens, private keys or runtime files. Do not create another account or reimport/reset data to make this test pass.

This is user-observed graceful application restart acceptance. The supplied source routes the actual Quit button through QUIT_GAME, do_gameloop return and safe_exit/exit. No ADB process capture is required for this manual step; no independent PID/termination measurement is claimed. The app profile is persisted separately from its memory-only session. Exiting the app is not a server logout operation; this test does not establish old-session revocation, which was acknowledged in the prior logout test. Backend/MongoDB restart persistence for this player and unavailable-service behavior are separate later tests. Custom campaign/team gameplay remains later implementation.
