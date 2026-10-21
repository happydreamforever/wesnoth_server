# Next test: create and view the first Alliance team

The user confirms that MongoDB, the admin service and the account bridge all restarted, followed by reopening the game and logging in again. The same player ID, Spearman, level 1 and both experience values of 0 returned. WAN stayed disconnected while local Ethernet remained connected. Accept account persistence across that restart at user-observed scope; do not repeat the accepted test.

This update adds **Teams** inside the existing Alliance menu: enabled areas, team lists, creation and the player's own roster. The creator becomes captain of a team with capacity 8. Joining teams, captain management, campaign rewards and team battles are later updates. Team experience is separate from personal-leader experience.

**The rebuilt Windows bridge is now READY at100.99.99.14:15001. Perform only the Android build below, then return its result.** The console confirms artifact verification and listener startup against the existing profile runtime. READY follows identity validation and authenticated backend health; it does not exercise the new team-directory routes. The user explicitly confirms the admin service was restarted after pulling the team update and before starting this bridge. No additional restart is needed. This startup's WAN state was not supplied; the previous bridge rebuild was explicitly confirmed WAN-disconnected.

This checkpoint changes project records only; no new pull is needed. Keep MongoDB, the admin service and the bridge running in their existing windows. Leave LDPlayer open with the game closed. Keep WAN disconnected and local Ethernet connected. Preserve the current account, runtime, identity, trusted profile, game data/OBB, saves, original native stages and backups. Do not repeat the completed bridge rebuild or database initialization.

## 1. Build the Android team update

Use a separate PowerShell window. The helper first verifies and preserves both completed account build stages, then builds APK1192602 offline. This command does not install the APK or change the running services.

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

The helper verifies and preserves the completed native account engine and account APK stages, then builds the updated sources using the existing pinned dependencies and offline Gradle cache. Expect **ANDROID ACCOUNT UPDATE PREPARED**, **ANDROID ACCOUNT GAME BUILD COMPLETE** and **ANDROID ACCOUNT GAME REBUILD COMPLETE**. **Stop here and return the build result and whether WAN stayed disconnected.** Installation follows review; on failure send `wesnoth_client\diagnostics\android-account-rebuild-*.txt` and the corresponding `android-account-build-*.txt` log. Preserve all backups and any reported lock; do not rename completed stages manually.

## 2. Later: install after build review

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

## 3. Later: create and retrieve the first team

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
