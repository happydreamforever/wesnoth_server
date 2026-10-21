# Next LDPlayer step: install Android1192604

The returned Windows log confirms1192604 built successfully: previous1192603 stages preserved, six native steps,33 offline Gradle tasks and final artifact/build/rebuild checks passed. The user explicitly confirms WAN was disconnected while local Ethernet remained connected. No additional pull, rebuild or service restart is needed now.

Keep the game closed, LDPlayer open and the MongoDB/admin/bridge windows running. Keep WAN disconnected and local Ethernet connected. Install using KeepSavedProfile to preserve the trusted server and existing app data. This phase verifies the update and setup screen; game notifications require the later manual test.

## Current phase: install while retaining the trusted server

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop
    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' -KeepSavedProfile
    if ($LASTEXITCODE -ne 0) { throw 'Android update installation failed. Send the saved install log.' }
}
```

Expected: verified version 1192604, ANDROID ACCOUNT GAME INSTALL COMPLETE, and LDPlayer shows Wesnoth Alliance / Trusted server: 100.99.99.14:15001 / Start game. The helper preserves app data and does not reimport the profile or copy an OBB. If the saved profile is missing/unusable, stop and report the message without resetting/reimporting. Stop at the setup screen and report the completion/version output plus whether Wesnoth Alliance, the existing Trusted server and Start game are visible. Return diagnostics/android-account-install-*.txt if installation fails. Do not start the manual notification phase until installation and the retained profile are confirmed.

## Phase 5: new rejection, unread notice and retained history

Keep WAN disconnected and local Ethernet connected throughout. Use the same LDPlayer and existing accounts; never send passwords.

1. Start game -> Alliance -> Log in as UniRecruit. Dismiss the profile. Under Teams, open My applications and confirm Koichi — 1/8 members. If no request is pending, inspect My team first; only if no team is present, submit one application through Browse areas and teams -> Yama -> Koichi -> Apply to join -> Send application -> Open. Confirm the refreshed pending entry. If UniRecruit already belongs to a team, stop and report instead.
2. Log out; log in as captain UniPlayer. Teams -> Review applications -> UniRecruit -> Open. Select **Reject application**, then confirm Reject this application for Koichi. Approval is a separate option: do not choose it in this rejection test. Expect Application rejected and the refreshed empty captain queue. My team remains 1/8 with the same captain/level/XP/rating. Stop and report this phase before switching back.
3. Log out; log in as UniRecruit. Dismiss Logged in. Expect **Unread application decisions** with **Unread — Rejected — Koichi** and a UTC time. Choose **Back** without opening the notice.
4. Teams -> My applications must offer the same unread notice again. Select it -> Open. Expect **Application rejected** and **The captain rejected your application to join Koichi**. Choose OK. This acknowledges only that decision, then My applications reports no pending requests. My team still reports no team.
5. Teams -> Application decisions now shows **Read — Rejected — Koichi**. Open it to confirm the saved result, then choose Back from the history and Teams menus. Logging out/in must not offer that read notice as unread; Application decisions must still retain it. Do not create repeated applications just to test notification count.

Report the login notice, Back/unread behavior, detail, retained Read status, no-membership state and whether WAN remained disconnected. A list/read failure is not proof of a lost decision. If acknowledgement is unconfirmed, reopen Application decisions to inspect the saved status before repeating anything.

## Next acceptance after the rejection notice

A later bounded handoff will reapply as UniRecruit and approve as UniPlayer, then verify the approval notice, matching2/8 roster on both accounts, unchanged personal/team XP and full-service restart persistence. No battle or campaign reward has been implemented by this update. Team leave/captain transfer UI, campaign progression and Alliance Battle follow the implementation checklist.
