# Current development and acceptance state

This note supersedes older checkpoint headings. Date2026-11-02.

## Current product

Emerald Court touch UI; current Android1192629. Protocol5/schema5/backend-worker1192626. The newer Court world uses128 geographic Areas and a reused64-Castle map, ten-member Teams, scheduled battles, competitions, normal Castle attacks, Crown wallets/shop/administration. Read `COURT_IMPLEMENTATION_1192626.md`, `COURT_PROTOCOL_1192626.md` and the current source for precise rules. The older Companies/Castles/world-round release1192624 plan is historical; do not restore its superseded behavior.

Client1192627 introduced retained smooth-map viewports, touch gestures and passive profile;1192628 introduced initial width fit, a single top toolbar and Cairo minus. Both received broad user acceptance.1192629 adds explicit blocked-action modals and Room validation. Server feedback correction sanitizes completed/cancelled descriptions for the native protocol and projects captain allowances for current members only. The precise cause of every reported Windows warning was not established; do not disable network/session validation to hide one.

Historical checkout references before the migration delivery commits (current transfer HEADs are recorded in migration/git/repositories.json):

- Client checkout HEAD `417255c53054475a555abb3a36d38541e874824f`; feedback implementation `f3623b182909cc70d679a39cc8fb56debfa34513`.
- Server checkout HEAD `8d06edd2cc59327e322fe5c5afbd2c859f960f8a`; Court projection implementation `da461109bdbf54c44768207cb627da52d2aecb08`; W05 correction `82e160437971f23c76c74af61a5c2933bf3bb6c5`.
- Both READMEs were already empty user modifications. Four server context files already had30 added lines each. Those pre-existing edits remain uncommitted and preserved. The new checkpoint notes and public migration helpers/recipes are committed separately; none of the pre-existing edits are included in those commits.

## Latest Windows evidence

1.1192629 preserving Android rebuild passed after an interrupted backup move. Keep originalWinError5/partial journal evidence. Its historical cause was not proved; do not remove locks or change ACLs speculatively.
2. Corrected five-service startup passed. Stem `alliance-workflow-20261102-080858-655-024f53673c7a4a4b87d995d29e6f0d2c`. W02Mongo/W03backend/W04bridge PASS existing; newW05 worker verification WAIT at31seconds, then PASS and `elapsed_seconds=56.093; health=healthy`; W06multiplayer START/PASS; W07allfive ready. This is actual supplied-console cold-start acceptance, not merely W05reuse. Old timeouts remain history;56seconds does not prove why earlier attempts exceeded300seconds.
3. User confirms WANdisconnected/localEthernetconnected once for restart/install batch. Do not ask again unless conditions change.
4. Latest installer passes prerequisite/engine/assets/original-signer checks, adb `Success`, installed1192629 and `OfflineInitActivity Status:ok` plus fresh startup marker. `ANDROID ACCOUNT GAME INSTALL COMPLETE`. Saved client log `diagnostics/android-account-install-20261102-082623-845-496da162cdf547e597a715e3716ad370.txt`. This log was pasted, not independently opened on Windows. No Windows APK hash or visual Login was supplied.

Windows workspace: `D:\Test\wesnoth-setup`. Runtime: `%LOCALAPPDATA%\WesnothAlliance\runtime-v3`. Python3.12.10x64. MSYS2root`D:\Test\wesnoth-setup\msys64`. Five-service launcher requires explicit runtime-v3; its older default runtime-v2 must not be used. AdminURL`http://127.0.0.1:18765/`; Mongo loopback27018; accounts15001/battles15002/Room15000 at saved local address100.99.99.14. These are the Windows installation's existing values, not instructions to expose the VPS publicly.

Primary player is **unione**; administrator **uni** is separate. Current owned-hero count/AvailableCrowns/HeldCrowns have not been reported for this update. Do not reuse historical0/1000 values or create another primary player.

## Next Windows action after migration

No new Windows pull, build, reinstall, migration, initialization, app reset, signer change or profile import is needed. Keep all five service windows and LDPlayer open.

First confirm loading reaches Login with no import screen; log into existingunione. Run **F1** from client `docs/COURT_FEEDBACK_1192629.md`: report actual owned-character count, AvailableCrowns, HeldCrowns and whether existing saves remain listed. Compare against the user's own recorded preupdate values; if not recorded, say so. Do not overwrite/load/delete saves merely to check listing.

After reviewing F1, proceed through F2–F7:

- F2: Team entry, Back and repeat reads; no generic unavailable warning solely from navigation.
- F3: Only if the current account still owns no hero, eligible unclaimedCastle→AttackCastle must show Action unavailable / Earn or unlock a hero before joining a battle. OK preserves location and creates no charge/hold/attack. Otherwise NOTRUN; do not remove heroes.
- F4: Existing seat and teamless branches only when already available. Do not create paid commitments to manufacture test conditions. Joining a seat before choosing a hero remains allowed.
- F5: Existing cancelled/completed/history details and refresh; no terminal-description protocol warning. Do not complete/cancel a battle just for this check.
- F6: RoomCreate invalid gold1001, income21, limitedturns0, emptyname, correcting other fields between checks. Show concise modal and preserve edits; typing alone nonmodal. Cancel before validCreate, no paidRoom.
- F7: World/Area map zoom/pan/back/width/toolbar/minus/camera; Quit→freshLogin and actualhero/wallet/save preservation.

Stop at the first unexpected result. Retain exact action/text/logs, reproduce and fix on the VPS, retest that step and affected regressions only. User has one LDPlayer instance; separate authenticated companions/native fixtures do not establish multiple-human or physical-touch usability. After Fchecks resume the first unaccepted Court acceptance step, not the entire historical A–Z workflow.

## Scope of migration verification

The package restores source and pinned inputs. It does not preserve installed environments, compiled object caches or every past raw screenshot/database fixture. Tracked verification JSON/Markdown retains historical results and limitations; selected current1192629raw evidence/render recipes/APKs/journals are archived separately. Paths to omitted historical build audits remain historical references, not claims those files transferred.

Environment scripts retain exact principal tool/source pins and safe inventories. Nine image recipes include one reconstructed account-integration recipe; apt-layer versions can drift and must be compared. No full clean environment or Android build is claimed for the new VPS. Follow environment smoke verification and then the clean Android/native guide. PNG/WebP was an isolated comparison; production images remainPNG. Never treat a skipped or fixture-only test as actual Windows gameplay acceptance.

## Migration commits and refreshed transfer

Public migration sources are tracked in the server at tools/vps-migration-package. These are archive-layout templates, not a complete private payload. Both repositories include the current installation/migration checkpoint. Current exact HEADs, branches, refs and retained uncommitted-patch hashes are in migration/git/repositories.json and adjacent bundle/ref files. The archive is regenerated after committing/pushing; no signing key, private ZIP, dependency cache or Git bundle is published to GitHub.
