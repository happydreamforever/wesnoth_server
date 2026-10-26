# Next Windows test — product release 1192621

Use the [complete A–Z checklist](PRODUCT_ACCEPTANCE_1192621.md). This coordinated update changes startup, native UI, Room and Team protocols, and explicitly migrates the existing **runtime-v2 from schema 2 to 3**. It does not create a replacement runtime.

**Current Windows status: A and B accepted; C–Z pending.** Previous 1192620 build and service confirmations remain historical. VPS verification and rendered previews are recorded in [PRODUCT_UI_1192621.md](PRODUCT_UI_1192621.md) and [VERIFICATION_1192621.json](VERIFICATION_1192621.json); they do not establish LDPlayer acceptance.

Continue with **C only**: keep all five services and companions stopped, temporarily connect to GitHub and use the MSYS2 fast-forward pull block in PRODUCT_ACCEPTANCE_1192621.md for server then client. Expect successful updates and both printed HEADs. Return the output, then disconnect WAN while retaining local Ethernet and record that state once for the upcoming batch. Do not discard README edits or run a build/migration yet. B verified 106 files / 232,394,949 bytes; retain its exact private backup destination `C:\Users\Uni\AppData\Local\WesnothAlliance\backups\before-1192621-20261026-034630-113-3305e9604950415fa42f97a85512fa51` for E and Z. No backup contents or new WAN measurement were supplied to the VPS.

The sequence is A stop, B cold backup, C coordinated pull, D public-only build reference, E resumable migration, F bridge/native/Android builds, G five-service startup, H in-place installation, then I–Z visible product/gameplay/recovery checks. Do not substitute the old interface-only rebuild sequence. Keep the exact B backup and both migration journals for E retries and Z's isolated schema-2 recovery drill.

Record WAN state once per batch; after C retain local Ethernet with WAN disconnected. Use one LDPlayer and separately authenticated companions where required. Stop at the first unexpected result and retain logs/state. Report the letter, expected and actual behavior, relevant diagnostic paths and actual emulator resolution for UI issues. We reproduce and fix on the VPS, then repeat that step and affected regressions only. Unexercised subchecks are NOT RUN.

No dependency upgrades, fresh initialization, profile reimport, OBB transfer, app-data reset or deletion of prior stages/journals is part of this release. Passwords, tokens, private runtime files, `.env` contents and backup archives remain local. The old checklist is retained in [INTERFACE_ACCEPTANCE_1192620.md](INTERFACE_ACCEPTANCE_1192620.md).
