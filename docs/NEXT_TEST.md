# Next test: log out and log in again

The user returned **Logged in.** for **UniPlayer**, **Spearman**, **Level 1**, **Experience 0** and **Total experience 0**. They explicitly confirm one wrong password was rejected, the separate **View personal leader** request returned the same player ID/values, and WAN was disconnected while Ethernet stayed connected. Those checks are accepted at user-observed scope; do not repeat the wrong-password test.

**Current step: confirm server logout and access the same account through a fresh login.** Keep the database, admin-service and account-bridge windows open, local Ethernet connected and WAN disconnected. No PowerShell command, pull, rebuild, reinstall, new account or repeated profile import is needed.

## 1. Log out and confirm server acknowledgement

1. Select **OK** to close the personal-leader message.
2. Select **Log out → Open**.
3. Expected exact message: **Logged out. The server has revoked this session.** Select **OK**; the menu should offer **Create player account / Log in**.

If instead the message says **The server did not confirm session revocation**, stop and report the complete message. The app clears its local session even when the server request fails, so the logged-out menu alone does not establish server acknowledgement.

## 2. Log in again and compare the saved leader

1. Select **Log in → Open** and use the same `UniPlayer` account and correct password. Do not create another account.
2. Expected: **Logged in.**, with the same player ID, **Spearman**, **Level 1**, **Experience 0**, **Total experience 0**.
3. Select **OK**, then **View personal leader → Open**. Expect the same username, on-screen player ID and leader values again.

**Stop with that profile visible.** Report the exact logout confirmation, whether repeat login/profile retrieval succeeded with the same ID/leader, and whether WAN stayed disconnected. If a step fails, send the exact displayed error and stop. Passwords, session tokens, `.env`, private keys and runtime configuration must stay private. The copied ID has an O/0 ambiguity; confirming equality on screen is sufficient.

This verifies logout acknowledgement and repeat account access. It does not directly replay the old session token or establish app/database restart persistence. App-restart and unavailable-service checks follow separately. Campaign rewards and team battle gameplay remain later integrations.
