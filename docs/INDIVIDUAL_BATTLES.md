# Individual battle rooms

Android release: **1192619**. Implementation, native VPS checks, offline Android build and preservation verification are complete. Windows/LDPlayer acceptance has not started.

Individual battles use the existing **Multiplayer** dashboard and authenticated native server on TCP 15000. Every signed-in player can browse the same dashboard, regardless of area, team or captain status. No additional login, database, server process or data pack is required.

A new individual room is a standalone map with 2–8 human player seats. The map determines the number of seats and temporary battlefield alliances; these are unrelated to permanent Teams membership. The creator chooses a room name, map, turn limit, starting gold and the existing fog/shroud/timer settings. Starting gold is equal for every seat. The room details show these rules before joining and again before Ready.

The user-confirmed automatic-start rule is **full room + every player Ready**. A player must own and select a campaign hero/form before Ready. A player with no unlocked heroes may browse; completing a story campaign checkpoint unlocks eligible heroes. Observers do not occupy a player seat or count toward readiness.

Room listings are pushed by the server and show waiting/full/starting/playing status, occupancy and readiness. Filters combine ordinary room/map search with room type, status, open seats, gold and turn limits. Joining a full, changed or already-started room is refused using its latest server revision. Reviewing a room does not reserve a seat.

Settings, hero and membership changes invalidate readiness. The server owns capacity, side ownership and the current revision. Only the host client prepares the normal engine start after receiving the server's current all-ready notification; the server validates the final settings and hero snapshot before accepting it. A dropped or replaced player cannot leave behind consent that starts a different battle.

Individual battles preserve normal Wesnoth recruitment, movement, combat, turns and local saves/replays. Selected heroes carry their permanent collection level and scaling into the match. Like existing ordinary Multiplayer, these battles award **no permanent hero XP, team XP or rating**. Campaign progression and permanent Team-battle rewards keep their existing rules.

Rooms are live native-server sessions. Host departure closes the waiting room; a server restart does not restore a waiting room or its Ready consent. Running rooms do not admit new player seats.

Standard multiplayer remains available for manual starts, computer-controlled sides and saved games. A saved individual battle resumes through this manual flow with its frozen hero/combat state, rather than waiting for a new automatic-start signal. Existing team plans and the shared Team service on 15002 are separate from these global rooms.

## Implementation and acceptance checklist

- [x] Global live dashboard and room filters.
- [x] Room creation, map-derived capacity and reviewed game settings.
- [x] Concurrent join/capacity/stale-revision protection.
- [x] Owned hero selection and explicit settings consent before Ready.
- [x] Readiness invalidation after rules, hero or membership changes.
- [x] Full-room automatic start through normal native engine preparation.
- [x] Departure, disconnect, host exit and running-room handling.
- [x] Separately authenticated computer-controlled companion for one-LDPlayer testing.
- [x] Actual VPS native server/engine verification and preserved Android build.
- [ ] Combined Windows 1192618 UX + 1192619 room acceptance from user reports.

## Test scope

A computer-controlled companion is another authenticated player account running a headless native engine inside the existing LDPlayer. It is not a second human or emulator. Its password is entered privately; credentials do not appear in command arguments or reports. The helper reviews the room and requires explicit Ready consent for the current revision. Changed room consent must not be silently renewed.

The complete command, expected-result, report and targeted-retest sequence is in [NEXT_TEST.md](NEXT_TEST.md). It includes the pending startup/input corrections and the new rooms in one A–Z batch. Preserve runtime-v2, players, heroes, teams, trusted profile, OBB, pinned tools and all completed build stages. Routine updates do not repeat database initialization.

VPS evidence: [VERIFICATION_1192619.json](VERIFICATION_1192619.json). Two real native engine peers completed two synchronized AI rounds in each of two tests, including changed-settings reconsent, with unchanged permanent hero data. The host choices and ending were scripted; the guest executes the production companion. Actual offline Android43-step native/33-task Gradle build, original-signer verification and preserved-stage checks pass. These results do not establish Windows input/rendering or multiple-human gameplay.
