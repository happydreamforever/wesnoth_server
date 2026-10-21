# Next test: create and view the first Alliance team

The user confirms that MongoDB, the admin service and the account bridge all restarted, followed by reopening the game and logging in again. The same player ID, Spearman, level 1 and both experience values of 0 returned. WAN stayed disconnected while local Ethernet remained connected. Accept account persistence across that restart at user-observed scope; do not repeat the accepted test.

This update adds **Teams** inside the existing Alliance menu: enabled areas, team lists, creation and the player's own roster. The creator becomes captain of a team with capacity 8. Joining teams, captain management, campaign rewards and team battles are later updates. Team experience is separate from personal-leader experience.

**The Windows Android team build has passed. Install the completed update below, then stop at the setup screen and return the result.** The returned log confirms preservation of both previous account stages, six native steps,33 Gradle tasks and final APK checks. The user explicitly confirms WAN stayed disconnected while local Ethernet remained connected. No repeated build or tool upgrade is needed.

This checkpoint changes project records only; no new Git pull is needed. Keep MongoDB, the updated admin service and the bridge running in their existing windows. Keep LDPlayer open with the game closed, WAN disconnected and local Ethernet connected. The existing account, identity, runtime, trusted profile, OBB/imported data and saves remain authoritative. The bridge READY and user-confirmed fresh admin process are already accepted; do not restart them for this installation.

## 1. Install using the saved server profile

Run this in a separate PowerShell window. It verifies the completed APK and updates the installed app in place:

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

**Stop at this setup screen.** Return the saved `wesnoth_client\diagnostics\android-account-install-*.txt` and confirm that **Wesnoth Alliance**, **Trusted server: 100.99.99.14:15001** and **Start game** are visible. Do not import the profile again. If the helper fails or the profile is missing/unusable, return the exact output/message before proceeding. Keep all backend windows running.

## 2. Later: open the game after installation review

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
