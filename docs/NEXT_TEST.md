# Next test: create and view the first Alliance team

The user confirms that MongoDB, the admin service and the account bridge all restarted, followed by reopening the game and logging in again. The same player ID, Spearman, level 1 and both experience values of 0 returned. WAN stayed disconnected while local Ethernet remained connected. Accept account persistence across that restart at user-observed scope; do not repeat the accepted test.

This update adds **Teams** inside the existing Alliance menu: enabled areas, team lists, creation and the player's own roster. The creator becomes captain of a team with capacity 8. Joining teams, captain management, campaign rewards and team battles are later updates. Team experience is separate from personal-leader experience.

**The 1192602 installation and saved trusted server are accepted. Perform the manual login/My team check below, then return its result.** The returned installer output confirms artifact verification, successful in-place APK installation, installed version and a fresh setup marker. The user explicitly confirms **Wesnoth Alliance**, **Trusted server: 100.99.99.14:15001** and **Start game** are visible. Installation WAN status was not supplied; the preceding build was explicitly confirmed WAN-disconnected.

Keep MongoDB, the admin service and the bridge running in their existing windows. Keep WAN disconnected and local Ethernet connected. Use the current installed app and saved profile. No PowerShell command, new pull, rebuild, installation, profile import, data copy, database initialization or service restart is needed.

## 1. Log in and read My team

1. In LDPlayer's **Wesnoth Alliance** setup screen, press **Start game** and wait for the game main menu.
2. Select **Alliance**. Select the **Log in** row and press **Open**, then enter the existing **UniPlayer** username and its private password. Press **Log in**. Do not create another player account.
3. Expect **Logged in.** with the same player ID, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**. Press **OK**.
4. Select **Teams** and press **Open**. The Teams menu should contain **Browse areas and teams**, **Create team** and **My team**.
5. Select **My team** and press **Open**. Expect **You do not belong to a team yet.** The following text explains that Create team makes you captain and joining another team comes in a later update.

**Stop at that message.** Return whether login shows the same player/leader values, whether the Teams menu appeared, the exact My team result and whether WAN stayed disconnected. This read verifies the first authenticated team-directory request; it creates no team and awards no experience. If My team already shows a roster, report its name/ID instead of creating another team. If the menu is missing, login fails or the service returns an error, return that message before changing/reinstalling anything. Keep passwords and session tokens private.

## 2. Later: create and retrieve the first team after My team review

Keep WAN disconnected and local Ethernet connected throughout this manual test. Use the current UniPlayer login and the existing **Area 1**. All selectors below require choosing the named row and pressing **Open**.

1. After the no-team result above has been reviewed, dismiss that message with **OK** to return to the Teams menu. If a team already exists, record its name and ID and report it before creating another.
2. Select **Browse areas and teams → Open**. Confirm that **Area 1** appears, select it and press **Open**. Expect **There are no active teams in Area 1 yet.** Dismiss with **OK**, then choose **Back** from the area selector to return to the Teams menu. If teams already appear, report the observation; an empty database is not required for future use.
3. Select **Create team → Open**, choose **Area 1 → Open**, and enter **UniAlliance** in the team-name field. Press **Continue**. On **Confirm new team**, verify the name and area, then select **Create this team → Open** once.
4. Expect **Your team was created. You are its captain.** The details should show **UniAlliance**, a new team ID, **Area 1**, **Team level 1**, **Team experience 0**, **Rating 1000**, **Members 1/8**, and roster **UniPlayer (captain) — Spearman, leader level 1**. Record the displayed team ID for comparison.
5. Dismiss with **OK**, then select **My team → Open**. Expect the same team ID, name, area, captain and values from a new server request. Dismiss with **OK**.
6. Select **Browse areas and teams → Open → Area 1 → Open**. Select the **UniAlliance** row and press **Open**. Expect the same team and roster. **More areas**, **More teams** and **Previous page** appear only when additional pages exist; select a navigation row and press **Open** to use it.
7. Dismiss with **OK**, choose **Back** from the team list, **Back** from the area list, then **Back** from the Teams menu. In the Alliance menu, choose **View personal leader → Open**. Expect the same player ID, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**. Creating a team does not award personal or team experience.

If creation is cancelled, times out or returns an uncertain response, **do not repeat Create team immediately**. Open **My team** first: the server may already have committed the creation. Report the exact message and the own-team result. A team permission/membership error should preserve the current login; an expired session requires a fresh login.

Stop at the personal-leader dialog. Return the team ID comparison, captain/roster/team values, unchanged personal-leader values and whether WAN remained disconnected. These observations establish the first team directory/creation slice only; joining, captain-management actions, campaign rewards and team battles are not implemented by this update. Never send passwords, session tokens, private keys or private runtime configuration. Running launchers finalize their transcripts when stopped; do not stop a healthy component just to finish its log.
