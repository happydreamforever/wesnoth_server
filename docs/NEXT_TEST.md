# Next Windows test: saved area, audit record and sign-out

The returned console confirms successful database and website re-launches without the previous launcher-lock error. The authenticated replica-set, schema, administrator and transaction-rollback checks pass again. You confirm that you created an area before these restarts and that WAN was disconnected while local Ethernet remained connected. The remaining check is that your area and audit record survived and the website enforces sign-out.

Keep both existing database and website windows open. Keep WAN disconnected and local Ethernet connected. This checkpoint changes documentation only: no pull, build, installation, initialization, recovery or additional restart is required.

## Open the local website

In a third normal PowerShell window, run:

```powershell
Start-Process 'http://127.0.0.1:18765/'
```

Alternatively, enter that URL directly in the Windows browser. Sign in as `Uni` with your existing password if prompted.

1. Open **Areas**. Find the area you created before restarting. Confirm its name and identifier match the earlier record. Do not create another area or recreate a missing one for this check.
2. Open **Audit log**. Find the corresponding **Action** `create_area`. Its **Target** must equal that area's identifier and its **Reason** should be `Create an area`. Actor and Target are identifiers, not usernames.
3. Click **Sign out**. Enter `http://127.0.0.1:18765/` in the address bar again rather than using Back. Expect the login page; the dashboard should require sign-in.

Expected: the same saved area and audit entry are present after restart, and fresh access after sign-out requires login. If the identifier was not recorded before restarting, report that rather than claiming an exact identifier comparison. If an area or audit entry is missing, report the missing item without recreating it. If the website fails, send its visible error and current website-console output.

Return the area name and whether its identifier matches, whether the audit Target matches, and whether fresh access after sign-out shows login. No passwords, cookies, private configuration or runtime files are needed. You may sign in again afterward; leave the database and website running.

The already saved database/website transcript paths were recorded from your output. Recovery-helper output was not supplied; if you already have diagnostics/alliance-runtime-recovery-*.txt, it can be shared later without rerunning recovery. The permanent operation.guard file is normal and must remain. Preserve the database, earlier logs/backups and all completed game builds/OBB. Android Alliance accounts/teams are not integrated yet.
