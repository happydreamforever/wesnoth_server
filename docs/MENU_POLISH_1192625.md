**Accepted on Windows by user report (2026-10-30): UI1–UI6 PASS.** Do not repeat this update or its accepted interface checks. The user next requests administrator-role acceptance; follow the current section of `ADMIN_MANAGEMENT_20261030.md`. Saved build/install logs and explicit WAN status were not included in the confirmation. The delivery instructions below are retained as history.

# Emerald Court menu polish — Android 1192625

This is a client presentation update. It adds Help beside Quit, reduces the home
profile panel, replaces the Campaign shield with an aged storybook symbol, and
removes the panel behind startup progress. The Emerald Court artwork, native
Help content, account behavior and game rules remain in place.

The five existing Windows services can stay running. Keep `runtime-v2`, protocol
4, schema 4, the installed Python 3.12.10, original Android signer and bundled
public server configuration. The update does not require a server pull, worker
or bridge rebuild, dependency preparation, migration or database initialization.
The previously delivered administration update has its own pending AD1–AD3
checks in `ADMIN_MANAGEMENT_20261030.md`; this menu update does not complete them.

The client update must contain implementation commit `6114fb8db4480c6af8806589b551a361e48cc5d8`.

## 1. Save and update the client

Finish any active network battle, save the current campaign and Quit the game.
Keep the existing LDPlayer instance open on its Android home screen.
Temporarily connect WAN for this client pull:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $menuBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $menuBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) {
        throw 'Client update stopped. Preserve local changes and send the output.'
    }
    & $menuBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client rev-parse HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Commit check stopped. Send the output.' }
}
```

Expect a fast-forward or already-up-to-date result and the new client commit.
Disconnect WAN again, keeping local Ethernet connected. Record this once for
this UI batch; WAN disconnection must not break local account access.

## 2. Rebuild and install in place

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Menu rebuild stopped. Preserve all stages and send the rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Menu installation stopped. Preserve app data and send the install log.'
    }
}
```

Expect the previous completed account stages to be retained, followed by:

- `ANDROID ACCOUNT GAME BUILD PASS`
- `ANDROID ACCOUNT GAME REBUILD COMPLETE`
- `Success` from Android installation
- `ANDROID ACCOUNT GAME INSTALL COMPLETE`, with version **1192625**

Use the exact saved paths printed under `wesnoth_client\diagnostics`:
`android-account-rebuild-*.txt`, `android-account-build-*.txt` and
`android-account-install-*.txt`. Do not delete previous stages or recovery
journals, reset app data, import a new profile or replace the OBB.

## 3. Check the affected screens by touch

Stop at the first unexpected result. Report its label, the expected and observed
behavior and the relevant saved log or screenshot. Keep passwords and private
runtime files out of reports.

| Check | Action | Expected result |
|---|---|---|
| UI1 | Watch startup, then log in to the existing account. | Same Emerald artwork and title. Only the progress bar and percentage appear over the background, without the old enclosing panel. Login opens after preparation; no import screen or login-result popup. A fast cached check may finish quickly. |
| UI2 | Inspect the upper-right profile, then open My Heroes and return. | Smaller, readable emerald profile shows the current username and correct owned-character count. Advancement forms are not counted as extra heroes. Long names fit using ellipsis. No player-level field. |
| UI3 | Tap the question-mark Help button beside Quit. Browse a topic and use its visible close control. | The built-in guide opens and returns to the same home screen without signing out. Utility order is Quit, Help, Preferences, My Heroes, Achievements. |
| UI4 | Inspect and tap Campaign. | The central parchment button shows an aged book representing stories. It opens the existing campaign browser; Back returns normally. |
| UI5 | Tap Load, Room, Team, Map Editor, Preferences, My Heroes and Achievements; return from each. | Existing destinations work, with unchanged Emerald styling. Existing campaign saves, heroes, forms and XP remain present. Do not start a reward-bearing game for this UI check. |
| UI6 | Tap Quit, reopen the app and log in again. | Quit closes the Android task. Reopening requires login and retains the same server configuration, account collection and saves. |

Return UI1–UI6 PASS/FAIL/NOT RUN, the build/install output and WAN status once.
VPS render/build evidence is separate from these actual Windows/LDPlayer checks.
On failure, retain all artifacts, reproduce/fix the issue on the VPS, then retest
that step and its affected regressions without repeating unrelated accepted work.

After these checks, complete pending administration AD1–AD3 if not already
reported, then resume World/Company **L** from `WORLD_MOBILE_ACCEPTANCE_1192624.md`.
Accepted I1–I3 and K1/K2/J1/J2/K3 remain historical evidence. K4/J3, worker native
play and territorial acceptance remain pending. Record actual hero/soldier
values before reward-bearing play; no numerical baseline has been supplied.
