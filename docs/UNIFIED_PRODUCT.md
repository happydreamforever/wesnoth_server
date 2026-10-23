# Unified game implementation and acceptance

This is the authorized successor to release 1192615. Implementation and VPS
verification are in progress; this document is not a release or acceptance claim.

## Agreed product

- One mandatory startup login/signup and one session for Campaigns, Heroes,
  Multiplayer and Teams. No second mode-specific login or generic starter choice.
- New accounts unlock named, controlled story heroes after a scenario victory.
  Ordinary recruited units stay campaign-local. Explicit canonical identities
  merge the same character across campaigns, never different characters merely
  sharing a name. Each hero has shared permanent XP and earned selectable forms.
- New story playthroughs retain their authored strength and mechanics. Permanent
  hero strength is used for multiplayer and team battles.
- At hero level L, the next level costs 5L²+15 XP. HP grows by 2% of base per
  additional level; damage per strike by 1%. Round half upward. Preserve native
  unit tier, movement, strike counts, resistances and innate abilities. There is
  no designed level cap; arithmetic and storage must remain checked.
- Campaign victory commits earned combat/supported script XP plus 20 XP to each
  eligible participating hero; defeat gives no persistent XP. Saves/checkpoints
  are account/run bound and idempotent. Genuine new playthroughs can earn again.
- Each player selects an owned hero/form before Ready. Selection changes clear
  readiness and captain approvals. Running snapshots and reward recipients stay
  fixed. Ordinary multiplayer gives no permanent XP/rating; team rewards remain.
- One Campaigns entry includes stories and Training. Hero selection, rewards,
  retries and history use the common account rather than separate Alliance flows.
- Fresh game database, including a new administrator, after a verified private
  cold backup. Retain old runtime for recovery, tools, assets, OBB and trusted
  connection. Never reset an already-created new database on rerun.

## Implementation checklist

- [ ] Versioned hero catalogue and explicit story identities/forms.
- [ ] Owned-hero schema, XP math, generation binding, selection and settlements.
- [ ] Startup authentication and unified menus without repeated login.
- [ ] Story XP ledger, account-bound save/recall/branches and victory delivery.
- [ ] Portable multiplayer hero definitions and level scaling.
- [ ] Hero choice before Ready in fixed plans and ordinary multiplayer.
- [ ] Strict-TLS native lobby admission through single-use account tickets.
- [ ] Admin hero inspection/correction, fresh start and recovery.
- [ ] Versioned Android/native build and checked five-service startup.
- [ ] Actual VPS backend/native/engine/Android build verification.
- [ ] Commit/push coordinated release with step-by-step Windows acceptance.
- [ ] Actual Windows/LDPlayer functional acceptance from returned user results.

## Report, fix and retest

Use one existing LDPlayer instance. Record WAN status once per test batch; retain
local Ethernet. Each step needs an exact command or UI action, expected result,
and a saved non-secret report. Stop at the first unexpected result. Analyze and
reproduce it on the VPS, fix and verify the affected behavior, commit/push, then
retest the failed step and affected regressions. Preserve unrelated accepted
results. VPS checks do not establish Windows rendering or multiple-human play.
