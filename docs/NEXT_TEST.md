# Next LDPlayer test: create a fresh rejection for the notification test

APK1192604 installation and setup startup passed. The user confirms Wesnoth Alliance, the existing Trusted server100.99.99.14:15001 and Start game are visible. The new notification behavior still needs game testing. Earlier1192603 rejection events were not saved, so this test requires one new captain decision.

Keep MongoDB, admin service and account bridge windows running. Keep WAN disconnected while local Ethernet stays connected. Use the existing app, Koichi team, captain UniPlayer and applicant UniRecruit. No pull, build, installation, profile import, OBB copy or database initialization is needed.

## Current phase: captain rejects the existing UniRecruit request

1. Choose Start game, then Alliance. Select Log in -> Open, enter the existing UniPlayer credentials, and choose Log in. Dismiss Logged in with OK.
2. Select Teams -> Open, then Review applications -> Open. Expect the Koichi application list containing UniRecruit. If the queue is empty or UniRecruit is missing, stop and report that screen; do not create a new account, submit another application or repeat a previous decision.
3. Select UniRecruit -> Open. In Review application, select **Reject application** -> Open. The first/default option is Approve application; choose the rejection option deliberately.
4. In Confirm rejection, verify UniRecruit and Koichi (team ID4cd736d3-dc6c-4c3d-a816-e7682b56db30). Select **Reject this application** -> Open.
5. Expect **Application rejected. The application list will now refresh.** Choose OK. Expect **There are no pending applications for Koichi.** If other applicants are present, report that result and leave them untouched.

Stop here and report the acknowledgement and refreshed queue, plus whether WAN remained disconnected. This phase creates the saved decision; it does not yet prove applicant notification delivery. If an error makes the mutation outcome uncertain, report it rather than repeating rejection.

## Following phase after captain confirmation: applicant notification

After dismissing the captain queue message, Back leaves Teams for Alliance. Log out, dismiss the server-revoked message, then log in as the existing UniRecruit. After Logged in -> OK, expect Unread application decisions with Unread — Rejected — Koichi and a UTC time. Choose Back without opening the notice.

From Alliance, Teams -> My applications must offer that unread notice again. Select it -> Open, verify Application rejected / The captain rejected your application to join Koichi, then choose OK to acknowledge only that decision. My applications then reports no pending requests. Teams -> Application decisions must retain Read — Rejected — Koichi. My team must still report no team. Opening a read detail requires OK before Back exits history.

Later acceptance checks logout/relogin and full restart history, then a new application/approval, matching2/8 roster and unchanged XP. These are separate handoffs. Preserve the current Yama reference fb010e4d-af74-4906-8ba6-5f096aaf90ec, both accounts, team, trusted profile and all completed stages/backups. Campaign rewards and Alliance Battle integration remain later milestones.
