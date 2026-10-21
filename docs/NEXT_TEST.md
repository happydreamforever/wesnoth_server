# Next LDPlayer test: UniRecruit checks the rejected request

Captain UniPlayer successfully rejected the application. The user confirms the refreshed captain list is empty and WAN stayed disconnected while Ethernet remained connected. My team still shows Koichi with the same team ID, UniPlayer captain,1/8 members, team level1/experience0/rating1000. Applicant-side rejection visibility remains to be checked.

**Current step: log in as UniRecruit and read the application and membership state.** Keep MongoDB, admin service and bridge windows running, WAN disconnected and local Ethernet connected. Use the existing accounts in the same LDPlayer. No pull, build, installation, profile import, OBB copy or database initialization is required.

1. Return to **Alliance** and **Log out** as UniPlayer. Expect **Logged out. The server has revoked this session.**
2. **Log in** as the existing **UniRecruit** account and dismiss the profile dialog.
3. Open **Teams -> My applications**. Expect **You have no pending team applications. Open My team to check whether you are already a member.**
4. Open **Teams -> My team**. Expect **You do not belong to a team yet.** The additional Create team/Browse areas suggestions do not require any action.

Stop here and report both dialogs. Remain logged in as UniRecruit. Do not create a team, apply again or approve anyone yet. If a request still appears or a team is returned, stop and send the exact message. These two reads verify that the captain's rejection is visible from the applicant's own account without granting membership.

## Later steps — wait for each handoff

After this applicant check, UniRecruit will apply again and captain UniPlayer will approve the request. Both accounts must retrieve the same two-member roster without XP changes; a later controlled full restart checks membership persistence. Those steps are not requested now.

The user confirms the actual Yama area-ID prefix is fb010e4d. The current reference is fb010e4d-af74-4906-8ba6-5f096aaf90ec, using the latest full dialog and this confirmation. Earlier ff010e4d records are superseded evidence; no database-ID change is established. The applicant checks above remain pending and unchanged.

Campaign rewards, leave/captain transfer, team battles and two-human battle synchronization remain later milestones. Preserve the current app, trusted server, Koichi/Yama, both players, runtime/identity and completed stages/backups.
