# Next step: choose the LAN MongoDB deployment

The Windows initializer passed Python 3.14.3 and pinned installed-file checks, then reported `Owned MongoDB did not start; inspect runtime/alliance/logs/mongodb.log locally.` No database log was supplied, so the startup cause remains unknown. Setup stopped before administrator prompts. It may already have created private configuration/credentials and data/log directories under `runtime\alliance`; preserve them. Do not repeat initialization, reinstall, delete runtime data or change Windows permissions while assessing the preferred LAN database.

## Current user direction and verified facts

The user asks to use the MongoDB connection in `.env` and explicitly confirms it is on their local network and remains reachable without WAN access. This is a user statement about Windows routing, not a completed disconnected connectivity test.

A credential-private, read-only VPS check of the configured connection passed authenticated ping and metadata queries:

| Check | Result |
| --- | --- |
| MongoDB version | 8.0.32 |
| Authentication | Passed |
| Deployment | Standalone |
| Logical sessions | Available |
| Shared credential scope | Broad; unsuitable as the long-term application credential |
| Database named in URI | No |

The current Alliance code uses multi-document transactions for membership, battle reservations and settlement. Standalone MongoDB cannot support those transactions; logical sessions alone do not change that. A replica-set deployment is required for the intended unsharded installation. See [MongoDB transaction requirements](https://www.mongodb.com/docs/manual/core/transactions-production-consideration/).

## Information needed now

The user has been asked how the shared MongoDB runs (Docker, Linux service or Windows service) and whether it stores other applications' data. Wait for those answers before choosing a server configuration or providing restart/conversion commands.

We can use the existing LAN database machine. If its MongoDB is shared with other applications, a separate Alliance replica-set instance on that machine is an option that preserves the existing service. If the existing instance is dedicated to this game, converting it can be assessed after its configuration/storage/backups are understood. Neither approach has been executed or finalized.

Use a dedicated Alliance database and an application login scoped to it. The current `.env` credentials are inspection/bootstrap input only, not credentials to embed in the Android app or reuse unmodified for application operation. Never run the current local initializer against an existing shared database; its lifecycle and schema setup assume exclusive ownership.

## Work still required

After selecting the deployment, implement an explicit external-database mode with separate configuration from the partial local runtime, a read-only Windows compatibility check with WAN disconnected, safe ownership-checked schema initialization and a dedicated application credential. External mode must not start/stop/reconfigure the shared MongoDB service. Keep the operator website on Windows loopback. The current Settings and CLI accept only the owned local instance, so editing a URI alone will not enable the LAN database.

No new Windows command, pull, package installation or Android rebuild is required at this assessment step. No remote data, database schema, users, roles or server configuration were changed. Keep `.env` and runtime credentials private. Local MongoDB startup diagnosis can resume later if needed; no private runtime upload is requested now.
