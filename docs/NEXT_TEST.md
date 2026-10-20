# Next test: create and view the first Alliance team

The user confirms that MongoDB, the admin service and the account bridge all restarted, followed by reopening the game and logging in again. The same player ID, Spearman, level 1 and both experience values of 0 returned. WAN stayed disconnected while local Ethernet remained connected. Accept account persistence across that restart at user-observed scope; do not repeat the accepted test.

This update adds **Teams** inside the existing Alliance menu: enabled areas, team lists, creation and the player's own roster. The creator becomes captain of a team with capacity 8. Joining teams, captain management, campaign rewards and team battles are later updates. Team experience is separate from personal-leader experience.

**Perform only step 1 now, then return its result.** Steps 2–4 are the later handoff reference; wait for review of each phase before continuing. Keep the current MongoDB runtime, player account, server identity, saved trusted profile, OBB, imported game data, saves and completed build stages. The helpers preserve the completed bridge and both completed Android account stages before replacing their active build directories. No dependency download or database initialization is part of this update.

## 1. Update the checkouts and rebuild only the account bridge

### Stop the game, bridge and admin service

1. In LDPlayer, dismiss the profile with **OK**, choose **Back to game**, then the main-menu **Quit**. Leave LDPlayer running.
2. In the account-bridge PowerShell window showing READY on port 15001, press **Ctrl+C once** and wait for its PowerShell prompt. Normal output includes **Alliance account bridge stopped.**
3. In the admin-service PowerShell window for port 18765, press **Ctrl+C once** and wait for its PowerShell prompt. An intentional interruption can report exit 130 or Stopped.
4. **Keep the MongoDB window on port 27018 running.** This update uses the same existing database and runtime.

If either stopped component does not return to its prompt, stop and send its output before rebuilding or starting another copy. Do not close its window forcibly or delete locks/runtime files.

### Pull while temporarily connected to GitHub

Run this in an available PowerShell window. Both checkouts already exist; use their existing MSYS2 Git.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    $bash = 'D:\Test\wesnoth-setup\msys64\usr\bin\bash.exe'

    foreach ($name in @('wesnoth_server', 'wesnoth_client')) {
        $repo = '/d/Test/wesnoth-setup/' + $name
        Write-Host "Updating $name"

        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' pull --ff-only origin main')
        if ($LASTEXITCODE -ne 0) {
            throw "Pull failed for $name. Stop here and send the output."
        }

        & $bash --noprofile --norc -c ('PATH=/usr/bin:$PATH /usr/bin/git -C ' + $repo + ' rev-parse --short HEAD')
        if ($LASTEXITCODE -ne 0) {
            throw "Could not read $name commit. Stop here and send the output."
        }
    }

    'Both updates completed successfully.'
}
```

If Git reports local changes, keep them and send the error. Do not reset or reapply old stashes. After both pulls succeed, **disconnect WAN again while keeping local Ethernet connected**.

### Rebuild the bridge offline

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_server' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAllianceBridge.ps1' `
        -MsysRoot 'D:\Test\wesnoth-setup\msys64'

    if ($LASTEXITCODE -ne 0) {
        throw 'Team bridge rebuild stopped. Send the saved rebuild and build logs.'
    }
}
```

Expected:

- **Completed bridge build preserved:** followed by a unique backup path.
- **ALLIANCE ACCOUNT BRIDGE ARTIFACT VERIFIED** and **ALLIANCE ACCOUNT BRIDGE BUILD PASSED**.
- **ALLIANCE ACCOUNT BRIDGE REBUILD PASSED**.

**Stop here.** Return both pulled commit IDs, the rebuild result and whether WAN was disconnected during the build. Send `wesnoth_server\diagnostics\alliance-bridge-rebuild-*.txt` and the corresponding `alliance-bridge-build-*.txt` if there is an error. Keep MongoDB running; the admin service and bridge remain stopped until the next reviewed phase. Do not rerun the preservation/rebuild step after a failure without reviewing its log.

## 2. Later: start the updated admin service and bridge

After step 1 has been reviewed, keep WAN disconnected and Ethernet connected. MongoDB should still be running in its existing window.

In the admin-service PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAlliance.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime')
```

Require **ALLIANCE DATABASE CHECK PASSED**, then **Alliance admin: http://127.0.0.1:18765/**. Leave that window running. Existing launcher wording that native account integration is a later milestone predates the accepted account tests; the new team directory still requires this updated service process.

In the account-bridge PowerShell window:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass `
    -File 'D:\Test\wesnoth-setup\wesnoth_server\tools\Run-WindowsAllianceBridge.ps1' `
    -RuntimeRoot (Join-Path $env:LOCALAPPDATA 'WesnothAlliance\runtime') `
    -MsysRoot 'D:\Test\wesnoth-setup\msys64'
```

Require **ALLIANCE ACCOUNT BRIDGE READY 100.99.99.14:15001 -> local account service**. Leave all three service windows open and return their startup results. On an error, stop at that component and send its output and corresponding `alliance-serve-*.txt` or `alliance-bridge-run-*.txt` log; do not initialize the database or replace the identity.

## 3. Later: rebuild and update the existing Android account game

After startup has been reviewed, use a separate PowerShell window. Keep LDPlayer and all three services running, WAN disconnected and Ethernet connected.

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Rebuild-WindowsAndroidAccountGame.ps1'

    if ($LASTEXITCODE -ne 0) {
        throw 'Android team update build stopped. Send the saved rebuild and build logs.'
    }
}
```

The helper verifies and preserves the completed native account engine and account APK stages, then builds the updated sources using the existing pinned dependencies and offline Gradle cache. Expect **ANDROID ACCOUNT GAME REBUILD COMPLETE**. Return the result before installation; on failure send `wesnoth_client\diagnostics\android-account-rebuild-*.txt` and the corresponding `android-account-build-*.txt` log. Preserve all backups and any reported lock; do not rename completed stages manually.

Once the build is reviewed, install the update while preserving the saved trusted server:

```powershell
& {
    $ErrorActionPreference = 'Stop'
    Set-Location 'D:\Test\wesnoth-setup\wesnoth_client' -ErrorAction Stop

    powershell.exe -NoProfile -ExecutionPolicy Bypass `
        -File '.\tools\Install-AndroidAccountGame.ps1' `
        -KeepSavedProfile

    if ($LASTEXITCODE -ne 0) {
        throw 'Android team update installation stopped. Send the saved install log.'
    }
}
```

Expect **ANDROID ACCOUNT GAME INSTALL COMPLETE**, verification of version **1192602**, and the setup screen with the existing **Trusted server**. This updates the installed app without transferring the OBB or reimporting a public profile. If the trusted server is missing or unusable, stop and return that message; do not clear app data or reimport it.

Choose **Start game**, then **Alliance → Log in → Open** and log in as the existing **UniPlayer**. Use its private password; do not create another account. Dismiss the login confirmation with **OK**. The Alliance menu should now contain **View personal leader**, **Teams** and **Log out**. Return the install log and whether that menu appears before the team test.

## 4. Later: create and retrieve the first team

Keep WAN disconnected and local Ethernet connected throughout this manual test. Use the current UniPlayer login and the existing **Area 1**. All selectors below require choosing the named row and pressing **Open**.

1. In Alliance, select **Teams → Open**, then **My team → Open**. Expect **You do not belong to a team yet.** Dismiss with **OK**. If a team already exists, record its name and ID and report it before creating another.
2. Select **Browse areas and teams → Open**. Confirm that **Area 1** appears, select it and press **Open**. Expect **There are no active teams in Area 1 yet.** Dismiss with **OK**, then choose **Back** from the area selector to return to the Teams menu. If teams already appear, report the observation; an empty database is not required for future use.
3. Select **Create team → Open**, choose **Area 1 → Open**, and enter **UniAlliance** in the team-name field. Press **Continue**. On **Confirm new team**, verify the name and area, then select **Create this team → Open** once.
4. Expect **Your team was created. You are its captain.** The details should show **UniAlliance**, a new team ID, **Area 1**, **Team level 1**, **Team experience 0**, **Rating 1000**, **Members 1/8**, and roster **UniPlayer (captain) — Spearman, leader level 1**. Record the displayed team ID for comparison.
5. Dismiss with **OK**, then select **My team → Open**. Expect the same team ID, name, area, captain and values from a new server request. Dismiss with **OK**.
6. Select **Browse areas and teams → Open → Area 1 → Open**. Select the **UniAlliance** row and press **Open**. Expect the same team and roster. **More areas**, **More teams** and **Previous page** appear only when additional pages exist; select a navigation row and press **Open** to use it.
7. Dismiss with **OK**, choose **Back** from the team list, **Back** from the area list, then **Back** from the Teams menu. In the Alliance menu, choose **View personal leader → Open**. Expect the same player ID, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**. Creating a team does not award personal or team experience.

If creation is cancelled, times out or returns an uncertain response, **do not repeat Create team immediately**. Open **My team** first: the server may already have committed the creation. Report the exact message and the own-team result. A team permission/membership error should preserve the current login; an expired session requires a fresh login.

Stop at the personal-leader dialog. Return the team ID comparison, captain/roster/team values, unchanged personal-leader values and whether WAN remained disconnected. These observations establish the first team directory/creation slice only; joining, captain-management actions, campaign rewards and team battles are not implemented by this update. Never send passwords, session tokens, private keys or private runtime configuration. Running launchers finalize their transcripts when stopped; do not stop a healthy component just to finish its log.
