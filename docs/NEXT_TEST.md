# Next Windows test — product release 1192621

Use the [complete A–Z checklist](PRODUCT_ACCEPTANCE_1192621.md). This coordinated update changes startup, native UI, Room and Team protocols, and explicitly migrates the existing **runtime-v2 from schema 2 to 3**. It does not create a replacement runtime.

**Current Windows status: A–Z pending.** Previous 1192620 build and service confirmations remain historical. VPS verification and rendered previews are recorded in [PRODUCT_UI_1192621.md](PRODUCT_UI_1192621.md) and [VERIFICATION_1192621.json](VERIFICATION_1192621.json); they do not establish LDPlayer acceptance.

Start with **A only**: save campaign work; finish or intentionally cancel current network battles using their supported controls; stop companions; Quit the app. Stop native Room server, shared battles, account bridge, backend and MongoDB with Ctrl+C, and wait for all five PowerShell prompts. Preserve all runtime files and app data. Report A before continuing with the private cold backup in B.

The sequence is A stop, B cold backup, C coordinated pull, D public-only build reference, E resumable migration, F bridge/native/Android builds, G five-service startup, H in-place installation, then I–Z visible product/gameplay/recovery checks. Do not substitute the old interface-only rebuild sequence. Keep the exact B backup and both migration journals for E retries and Z's isolated schema-2 recovery drill.

Record WAN state once per batch; after C retain local Ethernet with WAN disconnected. Use one LDPlayer and separately authenticated companions where required. Stop at the first unexpected result and retain logs/state. Report the letter, expected and actual behavior, relevant diagnostic paths and actual emulator resolution for UI issues. We reproduce and fix on the VPS, then repeat that step and affected regressions only. Unexercised subchecks are NOT RUN.

No dependency upgrades, fresh initialization, profile reimport, OBB transfer, app-data reset or deletion of prior stages/journals is part of this release. Passwords, tokens, private runtime files, `.env` contents and backup archives remain local. The old checklist is retained in [INTERFACE_ACCEPTANCE_1192620.md](INTERFACE_ACCEPTANCE_1192620.md).
