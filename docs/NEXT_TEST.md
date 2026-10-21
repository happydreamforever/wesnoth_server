# Next LDPlayer test: the captain rejects UniRecruit's application

UniRecruit's withdrawal succeeded, the refreshed application list became empty and My team still reported no team. Reapplication then succeeded and the user confirms the refreshed list shows Koichi — 1/8 members again. WAN remained disconnected with local Ethernet connected throughout this test. Captain rejection and approval remain untested on Windows/LDPlayer.

**Current step: reject the pending request as captain UniPlayer.** Keep MongoDB, admin service and bridge windows running, WAN disconnected and local Ethernet connected. Use the existing accounts in the same LDPlayer. No pull, build, installation, profile import, OBB copy or database initialization is required.

1. Return to **Alliance** and **Log out** as UniRecruit. Expect **Logged out. The server has revoked this session.** Then **Log in** as **UniPlayer** using the existing captain account and dismiss the profile dialog.
2. Open **Teams -> Review applications**. **Applications to Koichi** should list **UniRecruit**. Select that player and **Open**.
3. In **Review application**, verify the player is UniRecruit. Select **Reject application**, then **Open**. Approval is the first option; explicitly select rejection for this test.
4. In **Confirm rejection**, verify UniRecruit, Koichi and team ID **4cd736d3-dc6c-4c3d-a816-e7682b56db30**. Select **Reject this application**, then **Open**.
5. Expect **Application rejected. The application list will now refresh.** Dismiss it. The automatic refresh must say **There are no pending applications for Koichi.**
6. Open **Teams -> My team**. Expect the same Koichi/Yama team, **UniPlayer (captain)**, **Members: 1/8**, **Team level: 1**, **Team experience: 0**, and **Rating: 1000**.

Stop here and report whether UniRecruit appeared in the captain's list, the rejection message, the refreshed empty list and the unchanged team values. Remain logged in as UniPlayer. Do not approve anyone or submit another application yet. If the player/team differs or a step fails, stop and return its text. If the rejection outcome is uncertain, read Review applications and My team before repeating it; an absent request alone does not prove membership.

## Later steps — wait for each handoff

Next we will switch back to UniRecruit to verify the rejected request is absent from My applications and My team still reports no team. Then UniRecruit applies again and captain UniPlayer approves it. Both accounts must retrieve the same two-member roster without XP changes; a later controlled full restart checks membership persistence. Those steps are not requested now.

Campaign rewards, leave/captain transfer, team battles and two-human battle synchronization remain later milestones. Preserve the current app, saved trusted server, Koichi/Yama, both players, runtime/identity and completed stages/backups.
