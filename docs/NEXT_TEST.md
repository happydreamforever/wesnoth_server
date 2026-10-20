# Next test: create the first Alliance player account

The user reports the public-profile steps complete and explicitly confirms the game main menu with **Alliance**. This accepts manual setup at user-observed scope; no new log or explicit WAN status was supplied. Account connectivity, registration and login have not yet been tested.

**Current step: create one player account and return its confirmation.** No PowerShell command, pull, build, reinstall or repeated profile import is needed. Keep the database, admin-service and account-bridge windows open. Keep local Ethernet connected and disconnect internet/WAN for this account test.

## 1. Create the player account

1. On the game main menu, open **Alliance**, select **Create player account**, then choose **Open**.
2. Select **Spearman — Loyalists**, then **Choose leader**.
3. Enter a new player username, for example `UniPlayer`. Use 3–24 ASCII letters, digits or underscores. Keep administrator `Uni` separate.
4. Enter your own password of 12–128 characters and choose **Create account**. In the next dialog, repeat the same password and choose **Confirm password**. Do not send the password in reports.
5. Wait for the result. Expected: **Your player account was created.**, the chosen username and player ID, **Personal leader: Spearman**, **Level: 1**, **Experience: 0** and **Total experience: 0**. The message ends with **Choose Log in to continue.**

**Stop at this confirmation.** Report whether account creation succeeds, the displayed leader/level/experience and whether WAN was disconnected. Keep the player ID for comparison during the later login test. If an error appears, send its exact text. A timeout/cancellation may happen after creation reaches the server; do not repeatedly create accounts or change usernames to bypass it. Return that result so the next step can check the same account. Send relevant listener/install logs only if needed, without passwords, session tokens, `.env`, private keys or runtime configuration.

Successful registration should store one player account and its leader in the existing local MongoDB. This step does not yet establish repeat-login persistence or award campaign/team experience.

## 2. Later: login, leader persistence and logout

After registration is accepted, keep WAN disconnected, local Ethernet connected and all three backend windows running.

1. Choose **Log in**. One attempt with an intentionally incorrect password should fail without entering the player menu. Then use the correct password.
2. Expected: login confirmation with the same username, player ID and Spearman leader. Open **View personal leader** and compare those values with registration.
3. Choose **Log out**. Expected: `Logged out. The server has revoked this session.` The menu should return to **Create player account / Log in**.
4. Log in again and open **View personal leader**. Expected: the same player ID and leader; no duplicate account or new leader is created. Log out to finish.

Report wrong-password rejection, correct login, leader values, logout and repeat-login results, plus WAN status. App-restart and unavailable-service checks follow separately. Custom progression and team battle integration remain later milestones.
