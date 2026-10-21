# Next test: retrieve the saved Koichi team

The user confirms the initial **You do not belong to a team yet.** message and successful creation of **Koichi** in **Yama**. The returned roster shows UniPlayer as captain, Spearman at leader level 1, team level 1, team experience 0, rating 1000 and members 1/8. The user explicitly confirms WAN was disconnected while local Ethernet stayed connected during the no-team check and creation.

These are the actual team and area; the earlier UniAlliance/Area 1 names were examples. Keep Koichi and its membership. The creation reply is accepted; a separate post-creation lookup has not yet been reported.

## Current step: read My team again

Keep the game and all three Windows backend windows (MongoDB, admin service and account bridge) running. Keep WAN disconnected and local Ethernet connected. Use the current UniPlayer session. No PowerShell command or new delivery is needed.

1. Press **OK** on the team details dialog to return to the Teams menu.
2. Select **My team** and press **Open**.
3. Compare the returned details with this saved reference:

| Field | Expected value |
| --- | --- |
| Team | Koichi |
| Team ID | `4cd736d3-dc6c-4c3d-a816-e7682b56db30` |
| Area | Yama |
| Area ID | `ff010e4d-af74-4906-8ba6-5f096aaf90ec` |
| Team level | 1 |
| Team experience | 0 |
| Rating | 1000 |
| Members | 1/8 |
| Roster | UniPlayer (captain) — Spearman, leader level 1 |

**Stop at that dialog.** Return whether the team ID and every value match, plus whether WAN stayed disconnected. If an error or no-team message appears, send its exact text and keep the existing team, session and services intact. Do not create another team or reinitialize the database.

My team sends a new authenticated request and reads the saved account/team/roster. It does not reuse the creation reply, create a team or award experience. This checks subsequent retrieval with the current services running; it does not establish persistence through a restart.

## Later checks after this result

Use **Browse areas and teams → Open → Yama → Open**, then select **Koichi → Open**, and compare the same team ID and roster. Return through **Back** to Alliance and use **View personal leader → Open** to check the same player ID, Spearman, level 1, Experience 0 and Total experience 0. Team creation is not intended to award personal XP. A later team-persistence phase can verify the same stored team after a controlled restart; the earlier account-only restart test predates this team.

Joining teams, captain-management actions, custom campaign rewards and team battles remain later implementation slices. Preserve the installed APK, OBB/data, saved server profile, identity, runtime and build backups. Do not repeat creation, pulls, builds or installation for this manual check. Keep passwords, session tokens and private runtime files private.
