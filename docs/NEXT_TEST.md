# Next LDPlayer test: UniRecruit receives the approval notice

The user approved UniRecruit instead of rejecting the request. The captain's successful reply and subsequent Koichi roster show 2/8 members: UniPlayer (captain) and UniRecruit, both Spearman level 1. Team level 1, experience 0 and rating 1000 remain displayed. Preserve this valid membership and use its new approval decision for notification testing. The user explicitly confirms WAN stayed disconnected while local Ethernet remained connected throughout the approval and 2/8 roster check. Fresh rejection notification testing remains pending.

Keep MongoDB, admin service and account bridge windows running. Keep WAN disconnected while local Ethernet stays connected. Use the existing installed APK1192604, trusted profile and both existing accounts. No pull, build, installation, profile import, OBB copy or database initialization is needed.

## Current phase: receive the unread approval at login

1. Close the Koichi roster with OK. The captain queue refreshes automatically. If it says **There are no pending applications for Koichi.**, choose OK. If the application list is shown, choose Back without acting on another request.
2. From **Alliance teams**, choose Back to return to **Alliance**. Select **Log out -> Open**. Expect **Logged out. The server has revoked this session.** Choose OK.
3. Select **Log in -> Open**, enter the existing **UniRecruit** credentials and choose Log in. Dismiss the **Logged in.** player-profile dialog with OK.
4. Expect **Unread application decisions** containing **Unread — Approved — Koichi — <UTC time>**.

Stop on this list and report what appears, including whether WAN remained disconnected. Do not open/acknowledge the notice yet. If no notice appears, report the screen instead of creating another request or changing membership. This phase checks applicant delivery only; an approval message to the captain does not prove this notification appeared for UniRecruit.

## Following phases after the login notice is confirmed

Choose Back to leave the notice unread. Teams -> My applications should offer the same unread approval again. Open that notice, verify **Application approved.** and **The captain approved your application to join Koichi.**, then choose OK to acknowledge only it. Once unread notices are exhausted, My applications reports no pending requests. Teams -> Application decisions should retain **Read — Approved — Koichi**. My team should show the same Koichi ID and 2/8 roster. Separately inspect personal leader and both experience values; the captain roster alone does not establish personal XP.

Later check read-history and membership persistence through logout/app restart and full service restart. Fresh rejection notice acceptance requires a later separately planned nonmember request; do not remove UniRecruit or alter the existing membership to force that test. Keep Koichi ID 4cd736d3-dc6c-4c3d-a816-e7682b56db30 and the previously confirmed Yama reference fb010e4d-af74-4906-8ba6-5f096aaf90ec. The latest pasted area prefix contains a non-hex r and is not new verified ID evidence. Campaign rewards and Alliance Battle integration remain later milestones.
