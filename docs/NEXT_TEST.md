# Next LDPlayer check: existing captain and new team menu

Android1192603 installation and setup startup passed. The user confirms Wesnoth Alliance, the existing Trusted server100.99.99.14:15001 and Start game are visible. Installation WAN status was not separately supplied; the preceding Windows build was explicitly WAN-disconnected. Koichi's earlier offline persistence acceptance remains valid.

**Current step: verify the existing captain in the updated game.** Keep MongoDB, admin service and bridge windows open. Disconnect WAN while retaining Ethernet and LDPlayer. No pull, build, reinstall, profile import, OBB copy or database initialization is needed.

1. Choose **Start game**.
2. On the main menu, open **Alliance**, select **Log in**, then **Open**. Log in as the existing **UniPlayer** using the private password.
3. Dismiss the Logged in profile dialog. Open **Alliance -> Teams** (select Teams and Open).
4. Confirm the Teams menu includes **My applications** and **Review applications**.
5. Select **My team** and confirm the existing Koichi details.

Expected:

- Team **Koichi**, ID **4cd736d3-dc6c-4c3d-a816-e7682b56db30**, area **Yama**.
- **Members: 1/8**; **UniPlayer (captain)**; **Spearman, leader level 1**.
- **Team level: 1**, **Team experience: 0**, **Rating: 1000**.

Return the team values and whether both new menu entries are present. Compare saved IDs on screen; earlier pasted player/area IDs had transcription ambiguities. Stop on an unexpected error or changed team data and send that message. Do not create another team/account or apply/approve/reject/withdraw yet. The current check reads existing data only.

The remaining checklist below is for continuity; it is not a request to run every step now.

## Phase 5 — manual membership acceptance in the same LDPlayer

Installation and retained trusted-server display are accepted. The remaining checks will be handed off one at a time after the current existing-captain check. Keep WAN disconnected and Ethernet connected. Use the same LDPlayer by signing out and switching player accounts; another emulator is unnecessary for membership testing.

1. Start game -> Alliance -> Log in as existing UniPlayer. Teams -> My team must retain Koichi/Yama and its captain/values. Teams now includes My applications and Review applications. An empty application list is expected initially.
2. Log out with the server-revoked acknowledgement. Create one separate player, for example UniRecruit if available, with a private password and Spearman. Log in. Do not share the password and do not create another team.
3. Teams -> Browse areas and teams -> Yama -> Koichi. Open the team action list, choose Apply to join, review the selected team, then Send application. After OK, the refreshed My applications list must include Koichi. My team must still report no team; application alone does not grant membership.
4. My applications -> Koichi -> Withdraw application -> confirm. Koichi should disappear from that pending list and My team should still be empty. Apply again through Yama/Koichi.
5. Log out and log in as UniPlayer. Teams -> Review applications should show the second player. Reject that player using the confirmation dialog; the application should disappear and Koichi should remain 1/8.
6. Log in as the second player, verify no pending Koichi request and apply again. Return to UniPlayer -> Review applications and approve the intended player explicitly. My team must now show 2/8, with UniPlayer as the sole captain and the new player in the roster. Team level/XP/rating remain 1/0/1000.
7. Log in as the second player. My team must show the same Koichi ID, Yama and two-member roster, while My applications no longer includes the approved Koichi request. View personal leader must remain Spearman level 1, experience 0, total experience 0. Check UniPlayer's personal values are unchanged too.
8. After these observations pass, perform a controlled game/bridge/admin/database stop and restart against the same runtime. Fresh logins must retrieve the same roster and values. Record WAN status for this new test separately from earlier acceptance.

Report the actual dialogs and roster values after each handed-off step. Compare IDs on screen; earlier pasted player/area IDs contained transcription ambiguities. If a mutation reports an uncertain result, use My applications, My team or Review applications to read the saved state before taking another action. Never repeatedly tap approve/apply to compensate for a timeout.

VPS validation covers these protocol/database paths; actual Windows builds and LDPlayer interaction remain pending until returned evidence. Two-human battle synchronization, campaign progression, leave/captain transfer and match rewards remain later milestones.
