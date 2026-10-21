# Next LDPlayer test: withdraw and reapply as UniRecruit

UniRecruit successfully applied to Koichi. My applications shows Koichi — 1/8 members, while My team still reports no team. The applicant also sees the expected captain-only review message. The user explicitly confirms WAN was disconnected while local Ethernet stayed connected during these checks. No captain has approved this request.

**Current step: withdraw, verify removal, then reapply.** Stay logged in as **UniRecruit** in the same LDPlayer. Keep MongoDB, admin service and bridge windows running, WAN disconnected and local Ethernet connected. No pull, build, installation, profile import, OBB copy or database initialization is required.

1. Open **Alliance -> Teams -> My applications -> Koichi**. Choose **Withdraw application**.
2. In **Confirm withdrawal**, verify Koichi and team ID **4cd736d3-dc6c-4c3d-a816-e7682b56db30**. Select **Withdraw this application**, then **Open**.
3. Expect **Application withdrawn. The list will now refresh.** Dismiss it. The automatic refresh must say **You have no pending team applications. Open My team to check whether you are already a member.**
4. Open **Teams -> My team**. Expect **You do not belong to a team yet**. Do not create a team.
5. Open **Teams -> Browse areas and teams -> Yama -> Koichi -> Apply to join**. Verify the same team in **Confirm application**, select **Send application**, then **Open**.
6. Expect **Application submitted. Your captain must approve it before you join.** Dismiss it; the refreshed **My applications** list must again show **Koichi — 1/8 members**.

Stop here and report the withdrawal message, the intermediate empty application list/no-team result and the final pending Koichi entry. Stay logged in as UniRecruit; do not approve or reject anything yet. If any result differs, stop at that point and send the message. If a request's outcome is uncertain, read My applications and My team before repeating it.

## Later steps — wait for each handoff

After withdrawal/reapplication is accepted, switch to captain UniPlayer to inspect and reject UniRecruit's request. Then UniRecruit applies again and the captain approves it. Both accounts must retrieve the same two-member roster without XP changes; a later controlled full restart checks persistence. These captain decisions and restart checks are not requested now.

Campaign rewards, leave/captain transfer, team battles and two-human battle synchronization remain later milestones. Preserve the current app, saved trusted server, Koichi/Yama, both players, runtime/identity and completed stages/backups.
