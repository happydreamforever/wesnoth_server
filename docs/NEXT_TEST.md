# Next Windows step: send the retained MongoDB process logs

The returned startup reports confirm installed Python3.14.3/package pins and MongoDB8.0.32. MongoDB child PID19492 exits14 during first_start, before the first ping completes. The helper records cleanup not_needed and performs no synthetic write or restart. MongoDB [documents exit14](https://www.mongodb.com/docs/v8.0/reference/exit-codes/) as a fatal/uncaught-error exit; it does not identify the underlying cause. We cannot yet confirm a recurrence of the earlier sharing violation.

Read the existing logs from this exact failed test. No pull, reinstall, build, database restart or internet connection is needed for this step. Keep the partial game runtime and disposable test directory intact.

Run this in PowerShell:

```powershell
explorer.exe 'D:\Test\wesnoth-setup\wesnoth_server\build\alliance-mongo-startup-20261019-220233-428-d2627339c57f4d70a0c38631cb9e4a01\logs'
```

Expected result: File Explorer opens the retained test's logs folder. Attach these two full text files in the conversation:

- `mongodb-1.log` — MongoDB's own startup/error log.
- `process-1.log` — captured process output, including errors that may precede file logging.

An empty process log is useful information; if a file is empty or missing, report that rather than rerunning the test. Keep any binary crash dump locally. Do not attach the original game runtime, credentials or `.env`. We already have the wrapper text and JSON reports, so they do not need to be sent again.

After reading these logs, choose the smallest justified fix or next check. Actual database startup, authenticated replica-set initialization, transactions, admin website and Android account integration remain pending.
