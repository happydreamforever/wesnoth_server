# Court protocol 5

Release 1192626 uses the existing pinned TLS/gzip transport and public connection
profile. Account envelopes use `v:5`. The account, battle and native Room ports
remain 15001, 15002 and 15000. Health reports identify 1192626/schema 5. Old account
protocols are rejected with an update-required response. MongoDB and backend
HTTP remain loopback-only.

## Player requests

The two new account operations are `court_query` and `court_command`. Their body
has an independent `version:1` to permit reviewed evolution of Court records.

```json
{"v":5,"id":"0123456789abcdef0123456789abcdef","op":"court_query","token":"<session>","body":{"version":1,"query":"snapshot","payload":{}}}
```

```json
{"v":5,"id":"0123456789abcdef0123456789abcdef","op":"court_command","token":"<session>","body":{"version":1,"operation":"create_team","payload":{"command_id":"f7e94a50-245d-418c-a780-04e98b1ef8c6","name":"Emerald Guard","area_id":"A001","price_revision":0,"confirmation":"confirmed"}}}
```

The client allocates and retains one command UUID for one reviewed action. An
exact retry returns the original durable result. Reusing that UUID with different
content is a conflict; a different account cannot read or reuse the receipt.
Authentication and database generation are rechecked even for duplicates.
An uncertain network result is resolved through `command_status`, never by
silently issuing a new paid command.

Queries are: snapshot, areas, area, castle, my_team, teams, team, plans, plan,
competitions, competition, shop, wallet, notifications, history, command_status
and room_quote. Query results explicitly project public records. Team treasury,
pending applications and personal inbox/ledger records require the corresponding
membership or ownership. Historical battle access includes current participating
Team members and recorded participants/captains, even after leaving.

Commands are explicitly enumerated in `alliance/court/service.py` and mirrored by
the bridge/client `court_protocol.hpp`. Player dispatch cannot reach administrator,
worker, settlement or arbitrary domain methods. Payload fields, lengths, numeric
bounds, identifiers and reviewed revisions are checked before mutation.

All paid operations use current price revision plus confirmation. Holds move
available balance into held balance; they are captured, released or refunded by
the corresponding lifecycle, not an arbitrary client wallet update. Fees are
bound to the reviewed action/settings and generation. Native Room admission
consents are short-lived opaque tickets scoped to actor, create/join kind and
Room; they are removed from the scenario packet before serialization into game
history or saves.

Responses carry the actor and database generation, current server time and a
bounded data object. Native parsing rejects duplicate keys, invalid UTF-8,
excessive depth, concatenated gzip members and oversized frames/expansion. The
client additionally requires canonical serialized response JSON. Limits
remain 64 KiB compressed and 256 KiB expanded; Court command
payloads are further bounded to 64 KiB. Public error messages are static and do not
include raw exceptions, private runtime paths or credentials.

## Native service authority

The native Room server uses the existing scoped service-authenticated loopback
interface. `room_admit`, `room_leave`, `room_close` and `rooms_heartbeat` bind
charges and leases to its generation. Room and execution heartbeat batches each
contain at most 64 identifiers; every response must account for the complete
requested batch. Fee capture requires approved admission for every frozen human
side and an execution reservation for that Room.

The battle service schedules Court contracts through generation-bound native
worker leases. Human account admission and worker service admission remain
separate. A worker may execute only its assigned AI sides; a witness has no human
control. Durable synchronized command evidence is required before reward or
ownership settlement. Result receipts, XP additions, holds, item use, quota use,
ownership and history settle atomically and return the same durable receipt on
duplicate submission. Native terminal evidence does not claim complete public
client anti-cheat.

## Generation boundary

Fresh setup creates a new schema-5 database generation in runtime-v3. Session,
story checkpoint, Room ticket and battle contract identities from the archived
schema-4 runtime cannot cross into it. Setup does not rewrite old campaign saves
or replay bytes. New rewards require a new account and a campaign/battle begun
under the current generation. The old runtime is used only through deliberate
isolated recovery, never a mixed-release five-service stack.
