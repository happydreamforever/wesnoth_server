**Current Windows status (2026-10-27): 1192623 rebuild PASS; installation stopped before app changes.** All 49 native steps and 33 Gradle tasks passed, followed by package/original-signer verification. ADB endpoint `127.0.0.1:5555` refused the connection; the selected device was not found. Open the existing LDPlayer instance, wait for Android home, then rerun only `Install-AndroidAccountGame.ps1 -KeepSavedProfile`. Return INSTALL COMPLETE/version 1192623 output before UI1. No pull/rebuild/reset/server restart is required. If refusal repeats with Android home visible, stop and report it. The user confirms WAN was disconnected while local Ethernet stayed connected for this batch; record it once and do not ask again unless the network state changes. The full release update instructions below are historical for the already completed build; do not repeat them.

# Emerald Court acceptance — 1192623

This client-only visual update follows the uploaded Emerald Court design. The1192622 build/install was accepted, but its visual design was rejected; do not mark its UI1–UI10 accepted. Retain the accepted 1192621 A–M observations as historical evidence, including their limits: startup failure Retry/Close was NOT RUN, and empty-Owned guidance remains open feedback. The next gameplay check remains N, using existing campaign saves after this UI batch passes. Protocol, schema 3, rewards, account data and server services are unchanged.

## Update once

Save any current campaign, then Quit the game. Keep the five existing Windows services running. Use the existing `runtime-v2`, public configuration, signer, OBB and LDPlayer instance. Do not initialize or migrate the database, reimport a profile, reset app data or rebuild the bridge.

Temporarily connect for the client pull, using the existing MSYS2 installation:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $emeraldBash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'
    & $emeraldBash --noprofile --norc -c 'PATH=/usr/bin:$PATH /usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client pull --ff-only origin main'
    if ($LASTEXITCODE -ne 0) { throw 'Client pull stopped. Send the output; preserve local changes.' }
    & $emeraldBash --noprofile --norc -c '/usr/bin/git -C /d/Test/wesnoth-setup/wesnoth_client rev-parse --short HEAD'
    if ($LASTEXITCODE -ne 0) { throw 'Commit check failed. Send the output.' }
}
```

Expected: a successful fast-forward or already-up-to-date result, followed by the client commit. Existing README changes are preserved. Disconnect WAN while retaining local Ethernet, and report that state once for the following batch.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'
    if ($LASTEXITCODE -ne 0) {
        throw 'Emerald Court rebuild stopped. Send the saved rebuild/build logs.'
    }

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) {
        throw 'Emerald Court installation stopped. Send the saved install log.'
    }
}
```

Expected: old completed account stages retained, `ANDROID ACCOUNT GAME REBUILD COMPLETE`, then `ANDROID ACCOUNT GAME INSTALL COMPLETE` and verified version **1192623**. The existing signed public configuration remains authoritative. Logs are written under `wesnoth_client\diagnostics`; use the exact paths printed by the helpers. No new dependency download is required.

## Check the affected interface

Complete these checks in order, stopping at the first unexpected result. Report the check label, expected versus observed behavior, and relevant saved log or screenshot. Do not send passwords, private runtime files or backups.

| Check | Action | Expected result |
|---|---|---|
| UI1 | Open the installed game. | Emerald Court background, styled title, measured progress and percentage; no profile-import screen. Login appears after data preparation. |
| UI2 | Use harmless temporary mixed-case text with the Windows keyboard; check visibility, Create account and Back, then clear it before entering real credentials. | Correct case, usable focus, no reset-keyboard control or stacked forms. Back returns to Login. |
| UI3 | Log in to the existing account. | Home appears directly, with no login-result popup. Serif title, framed green profile, labeled bottom plaques and original citadel scenery match the reference. Artwork fills the screen. |
| UI4 | Inspect the upper-right profile. Open My Heroes and compare its owned characters. | Correct username and `Heroes: N`, including zero if applicable; advancement forms are not counted as separate heroes. No player-level field. |
| UI5 | Inspect the top controls and bottom controls. | Top: Quit, Preferences, My Heroes, Achievements. Bottom labeled plaques: Load, Room, Campaign, Team, Map Editor. Campaign has the larger parchment treatment; other plaques are emerald with ornate gold borders. Utility action names appear on hover/focus/hold. |
| UI6 | Tab/arrow through controls, use Enter, hover, and hold a control then release. | Predictable focus and tooltips, one ordinary activation, and no activation from a long press. Full long username is available through hover/hold. |
| UI7 | Open the eight browse destinations and return; reserve Quit for UI10. Inspect nested selection lists, confirmations and both default/Celes interface selections. View the existing saved scenario without completing a new victory. | Consistent emerald surfaces, gold leaf borders, cream text and parchment action highlights; all nine existing actions work. Campaign gameplay HUD, maps, units and editor canvas retain their prior rendering. |
| UI8 | Inspect existing heroes, progression and campaign saves; return home after a collection refresh. | Existing identities, selected forms, levels, XP and saves unchanged by installation. Profile count reflects the refreshed owned collection. |
| UI9 | While at a menu, stop only the account bridge, then trigger an account action. Restart the bridge normally. | Required-server loss returns to Login with a concise network warning. Login succeeds after recovery. WAN disconnection alone does not log out a locally connected player. |
| UI10 | Choose Quit; reopen, then use the authentication X. | Both exit paths close the Android task. Reopening requires login. Existing saved game and server configuration remain available. |

Use the normal existing bridge command for UI9:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime-v2') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Expected: `ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001`. Keep its window open. Do not restart another copy while the original bridge is still running.

## Report and resume

Send `UI1: PASS` through `UI10: PASS`, or stop at the first failure with its details. Include WAN status once and the rebuild/install log paths. These are Windows/LDPlayer observations; VPS fixture renders do not replace them.

On a failure, retain the app, build, logs and saved game. Reproduce and fix the issue on the VPS, deliver the correction, then retest that step and affected regressions. Do not repeat unrelated accepted work.

After this UI batch passes, resume the existing **N scenario-reward check** from the saved campaign. Record current owned heroes/forms/level/current XP/total XP. Retain a uniquely named manual save immediately before an eligible named hero’s legitimate scenario victory, complete it once, then retain the following scenario under a separate save. Report the exact campaign/scenario, checkpoint name and actual before/after hero values, including reopening stability. Stop before replaying that checkpoint: the next guided check uses it to verify duplicate protection. Do not restart the campaign, use an arbitrary older checkpoint, assume earlier illustrative values or create replacement accounts.
