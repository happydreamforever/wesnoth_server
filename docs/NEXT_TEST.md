# Correction accepted; practice and replay policy

The user confirms all1192610 correction A–H checks pass, with WAN disconnected while local Ethernet remains connected. Record this as user-observed acceptance. Do not repeat the correction checks, pull, rebuild or reinstall just for this documentation update. The currently installed app intentionally still permits practice on cancelled plans.

The current discussion is the user's proposed state behavior:

| Plan condition | Recommended action |
| --- | --- |
| Draft with invalid roster or missing approvals/readiness | Inspect/preparation only; no practice |
| Valid draft, both current captains approved, every selected player Ready | Selected player may start local AI practice |
| Running | No practice; real Join/Rejoin requires future shared battle integration |
| Cancelled | View history only; no practice |
| Completed | View result/history; Watch replay only if that battle has an actual retained recording |

All-player readiness is the explicit recommendation interpreting 'after readying'. No new persisted Ready state is necessary. Practice remains local, unranked and without account/team XP or rating. Finishing practice must not change the Alliance draft to completed.

These new rules are not implemented yet. Both current practice gates allow draft/cancelled snapshots regardless of consent. Implementing the restriction needs a fresh plan read before launch plus matching checks in the UI and launch validator. Completed Alliance records currently have no replay metadata, managed recording or retrieval path. The native engine's existing replay support is reusable, but it does not supply a recorded Alliance match automatically.

No new Windows command is required for this design response. Preserve the existing accounts, teams, completed builds, runtime/profile and game data. When the implementation is ready, follow the normal cycle: VPS checks -> explicit commits/push -> guarded MSYS2 pull -> exact Windows build/install commands and expected results -> combined user report. The accepted correction's prior build/test instructions remain in Git history at server3c3f3c8/client7df1901. Do not run the old practice checklist that assumes cancelled plans are eligible.
