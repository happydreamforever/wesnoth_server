# Next test: log in and retrieve the saved personal leader

The user returned the account-created screen for **UniPlayer**, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**. They explicitly confirm WAN was disconnected while local Ethernet stayed connected. The first real Android-to-Windows registration is accepted at user-observed scope. The copied player ID has an ambiguous O/0 character; compare the actual on-screen ID rather than that transcription.

**Current step: reject one incorrect password, log in correctly and retrieve the same leader.** Keep the database, admin-service and account-bridge windows open. Keep WAN disconnected and local Ethernet connected. No PowerShell command, pull, rebuild, reinstall or new registration is needed. Use the existing `UniPlayer` account.

## 1. Check login and personal-leader retrieval

1. Select **OK** to close the account-created message. If back at the main menu, open **Alliance**.
2. Select **Log in → Open**. Enter `UniPlayer` with an intentionally incorrect password, then choose **Log in**. Make only one incorrect attempt.
3. Expected: **Invalid username or password.** Dismiss it with **OK**. The menu should still offer **Create player account / Log in**.
4. Select **Log in → Open** again and use `UniPlayer` with the correct password. Expected: **Logged in.**, the same player ID and personal leader as registration, **Spearman**, **Level 1**, **Experience 0**, **Total experience 0**.
5. Select **OK**. The menu should say **Logged in as UniPlayer**, with **View personal leader / Log out**. Select **View personal leader → Open**.
6. Expected: the same username, player ID, Spearman and level/experience values. This is a separate authenticated request to the Windows service.

**Stop with the personal-leader result visible, before logout.** Report whether the incorrect password was rejected, correct login succeeded and the player ID/leader values match. Confirm WAN stayed disconnected during this test. If any step fails, send its exact error text and stop; do not register another account or keep retrying passwords. Do not send passwords, session tokens, `.env`, private keys or private runtime files. The exact player ID need not be transcribed; an on-screen equality check is sufficient.

This test checks credentials and retrieval of the account saved during registration. It does not establish database/app restart persistence. Custom campaign/team rewards are not available yet.

## 2. Later: logout and repeat login

After the login/profile result is accepted, select **Log out**. Expected: `Logged out. The server has revoked this session.` The menu should return to **Create player account / Log in**. Log in again and compare the same player ID and leader, then log out to finish. App-restart and unavailable-service checks follow separately. Do not perform this section until the current result is accepted.
