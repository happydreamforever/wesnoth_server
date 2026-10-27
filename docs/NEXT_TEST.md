# Next Windows test — Emerald Court 1192623

The user rejected the 1192622 visual design; its completed Windows rebuild/install remains accepted at that scope. The replacement follows the uploaded Emerald Court reference. **1192623 Windows acceptance is pending.**

Use [EMERALD_ACCEPTANCE_1192623.md](EMERALD_ACCEPTANCE_1192623.md) for exact commands, expected markers, log locations and ordered UI1–UI10 checks. This is a client-only update. Save the current campaign and Quit; keep all five existing services and the schema-3 `runtime-v2` running.

1. Pull only the client using the existing MSYS2 Git; record its commit and preserve local README edits.
2. Disconnect WAN while retaining local Ethernet. Record network status once for this new batch.
3. Run the existing preserving Android rebuild, then install in place with `-KeepSavedProfile`. Expect `ANDROID ACCOUNT GAME REBUILD COMPLETE`, `ANDROID ACCOUNT GAME INSTALL COMPLETE` and version **1192623**.
4. Check startup/Login, the reference-based home, all nine actions, profile accuracy, default/Celes and nested menu surfaces, unchanged heroes/saves, network recovery and Quit/reopening.
5. Stop at the first unexpected result. Retain logs/state, reproduce and fix on the VPS, then retest only that step and affected regressions.
6. After UI1–UI10 pass, resume pending **N** using the existing campaign saves. Record actual before/after hero values and retain a pre-victory checkpoint; report one legitimate scenario completion before the guided duplicate check.

No server rebuild, database migration/initialization, account reset, profile reimport, OBB transfer or dependency upgrade is required. Preserve historical 1192621 A–M functional evidence and its limits. The 180 VPS native captures and offline APK verification do not replace LDPlayer acceptance.

---

## Historical workflow, superseded by the Emerald Court instructions above

**Current Windows status (2026-10-27):1192622 rebuild and installation PASS.** The returned console verifies49 native steps,33 Gradle tasks, original signer, successful in-place installation and version1192622 startup launch. WAN-disconnected/local-Ethernet is explicitly confirmed once for this batch. Next is **UI1** in the installed app: citadel background/title/progress and eventual Login, with no import step or visual error. No new pull/build/install/service restart is needed for this documentation-only record. UI1–UI10 and subsequent N remain pending; follow the visible checks below without repeating the completed update commands.

# Next Windows test — Citadel menus1192622

Use [CITADEL_ACCEPTANCE_1192622.md](CITADEL_ACCEPTANCE_1192622.md) for exact commands, expected outputs, report paths and UI1–UI10. This is a **client-only** update; keep the existing five services and schema3 runtime-v2. Save the current campaign and Quit before updating.

1. Pull only the client with existing MSYS2 Git and report its commit. Preserve local README changes.
2. Disconnect WAN while retaining local Ethernet; record this once for the new batch.
3. Run Rebuild-WindowsAndroidAccountGame.ps1, then Install-AndroidAccountGame.ps1 -KeepSavedProfile. Expect retained old stages, REBUILD COMPLETE, INSTALL COMPLETE and verified1192622.
4. Check startup/authentication, home composition and icons, profile count, all native destinations/default+Celes, saved hero/campaign values, required-local-server-loss recovery and Quit/reopen. Keep names/passwords/private backups out of diagnostics as appropriate; never send passwords or private runtime files.
5. After UI1–UI10 pass, resume **N** from the existing campaign save. Record actual hero values, retain a unique pre-victory checkpoint, complete one legitimate eligible scenario, preserve the following scenario and report before/after values. Stop before repeating victory so the duplicate check uses this exact checkpoint.

No server/bridge rebuild, database migration/initialization, dependency upgrade, profile import, OBB transfer or app reset. The deliberate account-bridge stop/restart in UI9 is the only service interruption. One LDPlayer remains sufficient for these UI checks.

[VPS verification](VERIFICATION_1192622.json) passes actual native renders at1280x720/1920x1080, offline Android compilation/package/signer checks and preservation inventories. Windows/LDPlayer acceptance remains pending. [Design and previews](CITADEL_UI_1192622.md) use fixture data, not current player values.

Historical1192621 A–M observations remain accepted at their recorded scope. Startup failure Retry/Close remains NOT RUN and empty-Owned guidance remains open feedback. N–Z gameplay acceptance remains pending. Stop at the first unexpected result; retain logs/state, fix on VPS, then retest the failed step and affected regressions without repeating unrelated accepted work.

## Historical1192621 handoff (superseded by the client-only update above)

# Next Windows test — product release 1192621

Use the [complete A–Z checklist](PRODUCT_ACCEPTANCE_1192621.md). This coordinated update changes startup, native UI, Room and Team protocols, and explicitly migrates the existing **runtime-v2 from schema 2 to 3**. It does not create a replacement runtime.

**Current Windows status: A-M's requested functional checks accepted; N-Z pending. Main-menu redesign and empty-Owned guidance remain open.** Previous 1192620 build and service confirmations remain historical. VPS verification and rendered previews are recorded in [PRODUCT_UI_1192621.md](PRODUCT_UI_1192621.md) and [VERIFICATION_1192621.json](VERIFICATION_1192621.json); they do not establish LDPlayer acceptance.

**Immediate next action — N scenario reward:** the user explicitly confirms L1-L4 and M PASS. Preserve their accepted filters/search/locked and owned detail checks, campaign previews/Cancel/no Hero training and unchanged progress. Deoran/Cavalryman was last reported at permanent level3, Experience9, Total earned64; use current observed values as the next baseline if further play has occurred. I's startup failure Retry/Close remains NOT RUN; the earlier empty-Owned guidance gap and main-menu redesign remain deferred UI feedback.

In the same signed-in account, record current Owned hero names/forms/level/Experience/Total earned, then use Load to resume the existing campaign. Before the next legitimate victory with an eligible named hero, retain a uniquely named manual save such as 1192621-N-before-victory. Finish once; retain the following scenario under a different save before returning to My Heroes. Report the exact campaign/scenario title, before-victory save name, actual before/after hero values/forms and any error. Story rewards submit automatically; no separate Send completed result control is required. Loading and unfinished play alone must not grant rewards. Keep the pre-victory save and private campaign records; stop after this report before repeating the victory for N's duplicate check. Do not restart the campaign, replay an entire old scenario, infer Deoran's presence, create an account or grant artificial rewards. No build/install/restart is needed.

Full N reward attribution and duplicate protection remain pending. The subsequent duplicate check must use this retained checkpoint: an arbitrary older victory can fail the latest-transition guard after the campaign has advanced. A client completed-checkpoint guard and transactional backend receipt exist and were verified on the VPS, but those do not establish this Windows acceptance. Keep all five services and the existing WAN-disconnected/local-Ethernet batch state.

The sequence is A stop, B cold backup, C coordinated pull, D public-only build reference, E resumable migration, F bridge/native/Android builds, G five-service startup, H in-place installation, then I–Z visible product/gameplay/recovery checks. Do not substitute the old interface-only rebuild sequence. Keep the exact B backup and both migration journals for E retries and Z's isolated schema-2 recovery drill.

WAN disconnected/local Ethernet retained is explicitly confirmed after C for this batch; record later changes only. Use one LDPlayer and separately authenticated companions where required. Stop at the first unexpected result and retain logs/state. Report the letter, expected and actual behavior, relevant diagnostic paths and actual emulator resolution for UI issues. We reproduce and fix on the VPS, then repeat that step and affected regressions only. Unexercised subchecks are NOT RUN.

No dependency upgrades, fresh initialization, profile reimport, OBB transfer, app-data reset or deletion of prior stages/journals is part of this release. Passwords, tokens, private runtime files, `.env` contents and backup archives remain local. The old checklist is retained in [INTERFACE_ACCEPTANCE_1192620.md](INTERFACE_ACCEPTANCE_1192620.md).
