# Next test: identify current handles to the MongoDB metadata file

The returned MongoDB startup log identifies the immediate failure. Windows refused to rename `WiredTiger.turtle.set` to `WiredTiger.turtle` because a conflicting file handle was open. Deleting the `.set` file then failed with the same sharing error, and WiredTiger stopped with `WT_PANIC` / fatal assertion `50853`. This occurred during storage initialization, before administrator prompts. The log does not identify the process responsible or establish database corruption.

## Do this one observational step

No pull, internet access, download, build or reinstall is needed. Keep MongoDB stopped.

1. Open Windows **Start**, type **Resource Monitor**, and choose **Run as administrator**. Accept the Windows prompt for this inspection.
2. Open the **CPU** tab and expand **Associated Handles**.
3. Clear any selected process checkboxes in the **Processes** section so they do not restrict the search.
4. Enter `WiredTiger.turtle` in **Search Handles** and wait a few seconds.
5. Send the matching **Image**, **PID** and **Handle Name** values. Include the path so we can distinguish the files under `D:\Test\wesnoth-setup\wesnoth_server\runtime\alliance\data` from unrelated files. If nothing appears, reply **no matching handles**. If inspection is blocked, send that message instead.

This is a new search for the current database files, not a repeat of the old Git/service experiment. The built-in workflow is described in [Microsoft's Resource Monitor guidance](https://techcommunity.microsoft.com/blog/itopstalkblog/identify-which-process-is-blocking-a-file-in-windows/4432635). Leave processes and handles open; do not use End Process. The inspection does not need MongoDB to start again.

A match identifies a current user of the file, not necessarily the process that blocked the earlier rename. No matches cannot rule out a transient conflict that disappeared after MongoDB crashed. Neither result establishes a fix. We will choose the next diagnostic from the returned evidence.

## Preserve the current installation

Do not delete or rename WiredTiger files, remove lock files, run MongoDB repair, clear the runtime, or disable/stop unidentified software or services. Keep the crash dump locally; it is not needed for this step and should not be uploaded. Do not send `.env`, private configuration/key files or the entire runtime folder.

Use the already installed local MongoDB 8.0.32 on `127.0.0.1:27018`; the `.env` internet server is not part of the offline deployment. Initialization, administrator website checks and disconnected database operation remain pending. The installed Android game, OBB, guest LAN gameplay milestone, MSYS2 and completed native stages remain preserved.

This delivery records the log diagnosis and next observation only. No production implementation changed, no database repair was attempted, and no Windows startup success is claimed.
