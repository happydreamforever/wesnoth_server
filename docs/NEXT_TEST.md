# Next test: import the public server profile

The user confirms successful account APK installation and the visible **Wesnoth Alliance** setup screen. This is user-reported acceptance; the raw install log and exact filename have not been supplied. Installation WAN status is unreported. The previous build had internet available. Account connection/login has not yet been tested.

**Current step: import the transferred public profile and reach the Alliance main-menu entry.** No PowerShell command, pull, rebuild or reinstall is needed. Leave LDPlayer and the database, admin-service and account-bridge windows open. Keep local Ethernet connected and disconnect internet/WAN for the runtime test.

## 1. Import the public profile and open the game

Use the address, fingerprint and Downloads filename printed by the successful installation command (also saved in its `wesnoth_client\diagnostics\android-account-install-*.txt` log). Do not rerun installation to display them again.

1. In LDPlayer, choose **Import server profile**.
2. In the Android file picker, open **Downloads** and select the exact `wesnoth-alliance-public-profile-<id>.json` filename printed by the installer. If the picker opens in Recent, use its navigation menu to open Downloads.
3. In **Trust this Alliance server?**, compare the address with the installer's `Server:` line. The existing server is `100.99.99.14:15001`. Compare the entire **Certificate SHA-256** value with the installer's corresponding line.
4. If both match, choose **Trust server**. Expected setup status: **Trusted server: 100.99.99.14:15001**, followed by the fingerprint. If a value differs or the profile cannot be selected/imported, stop and return the displayed error; do not approve a mismatch.
5. Choose **Start game**. Let the app check and reuse the existing game data. At the main menu, look for **Alliance**, which replaces the former Add-ons entry.

**Stop at the main menu.** Confirm the trusted-server status and visible Alliance entry, and report whether WAN was disconnected during these steps. If anything fails, send the displayed error and the saved installation log. Never send passwords, server private keys or private runtime configuration. This confirms profile import and UI startup only; it does not yet establish account connectivity or successful authentication. Account creation is the next step after this result.

## 2. Later: manual account acceptance with WAN disconnected

Keep local Ethernet connected, WAN disconnected, and all three Windows backend windows running.

1. Open **Alliance → Create player account**.
2. Choose **Spearman — Loyalists**.
3. Enter a new player username, for example `UniPlayer`, and your own password of 12–128 characters. Repeat that password when asked. Use a player account separate from the administrator `Uni`. Do not send the password in reports.
4. Expected: account-created confirmation with the chosen personal leader, level **1**, experience **0** and a player ID.
5. Choose **Log in**. One attempt with an intentionally incorrect password should fail without entering the player menu. Then use the correct password.
6. Expected: login confirmation and the same username, player ID and Spearman leader. Open **View personal leader** and check those values.
7. Choose **Log out**. Expected: `Logged out. The server has revoked this session.` The menu should return to **Create player account / Log in**.
8. Log in again and open **View personal leader**. Expected: the same player ID and leader; no duplicate account or new leader is created. Log out to finish.

The server stores the account and personal leader in the existing local MongoDB. This milestone does not yet award campaign experience or implement team battles.

Report the visible results for registration, wrong-password rejection, correct login, personal leader, logout and repeat login, plus whether WAN was disconnected throughout. Send the relevant build/install/listener logs if anything fails. Do not send passwords, session tokens, `.env`, server private keys or private runtime configuration files.
