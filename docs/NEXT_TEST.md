# Next LDPlayer test: approval read status, pending list and personal experience

UniRecruit's unread approval list and opened detail now pass by user report, including matching Koichi team ID. The subsequent My team view matches the captain's 2/8 roster, team level 1, experience 0 and rating 1000. The user explicitly confirms a date/time is visible in the actual detail and WAN stayed disconnected while local Ethernet stayed connected. Missing timestamp text in the pasted report does not establish a rendering defect. Opening the detail alone does not confirm read acknowledgement; Back preserving unread was not reported and remains unconfirmed.

Keep the existing UniRecruit session, installed APK1192604, trusted profile and all three backend windows running. Keep WAN disconnected and local Ethernet connected. No pull, rebuild, installation, profile import, OBB transfer, database initialization or new application is needed.

## Current phase: inspect saved read status and unchanged personal progression

1. Close the current My team roster with **OK**. In **Alliance teams**, select **Application decisions -> Open**.
2. Inspect the list without opening the detail. Expect **Read — Approved — Koichi — <UTC time>**. If it is still Unread, absent, or an error appears, stop and report the screen. Do not reopen/acknowledge it again before reporting; this check should establish the saved outcome of the earlier detail interaction.
3. If the notice is Read, choose **Back**, then **My applications -> Open**. Expect **You have no pending team applications.** If an unread notice appears instead, stop/report without opening it. This verifies that the read approval is not offered again in this path.
4. Choose **OK**, then **Back** from Alliance teams to Alliance. Confirm **Logged in as UniRecruit**, then select **View personal leader -> Open**.
5. Expect **Player: UniRecruit**, the same existing player ID, **Personal leader: Spearman**, **Level: 1**, **Experience: 0**, **Total experience: 0**.

Stop at the profile and return the read/unread label, pending-list result and personal leader values, with whether WAN stayed disconnected. This bounded phase does not restart any service or modify membership. A displayed team experience of zero does not substitute for a personal experience check.

## Later phases

After these checks pass, verify read history and membership through logout/login, app restart and a controlled full backend restart. A fresh rejection notice and Back preserving unread need a separately planned pending request later; keep UniRecruit's approved membership. Do not remove a member, reapply or fabricate old history to recreate the earlier rejected request. Preserve Koichi ID 4cd736d3-dc6c-4c3d-a816-e7682b56db30 and the previously confirmed Yama reference fb010e4d-af74-4906-8ba6-5f096aaf90ec. The repeated pasted fr010e4d prefix is not a valid UUID and does not establish a database mutation. Campaign rewards and Alliance Battle integration remain later milestones.
