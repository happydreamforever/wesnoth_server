# Windows development settings in one file per project

Each checkout now has `dev.ps1` and a public `.env.example`. Each computer has
one private `.env` in `wesnoth_server` and another in `wesnoth_client`.
Run commands from that project's directory in Windows PowerShell 5.1.
Normal operation needs only:

```powershell
# wesnoth_server
.\dev.ps1 start
# wesnoth_client
.\dev.ps1 build
```

`start` checks the saved database endpoint, selected TLS identity, pinned service
Python/dependencies and existing five-service workflow. It starts missing healthy
services in order and reuses verified listeners. It includes battles, native
workers and Room. Failure stops progression and retains service windows/evidence.
`build` checks tools, offline Gradle, public server identity, original Windows
signer/reference APK; verifies completed foundations or builds missing ones in
order; prepares game data; packages the base and account APKs offline. An existing
account update must use `build -Update`, the established preserving update helper.
Completed foundations with mismatched receipts are refused for review.

## Set up a new computer

1. Use fresh checkouts of **both updated repositories**, preferably as sibling
   `wesnoth_server` and `wesnoth_client` directories. Bring verified input caches
   and game data; rebuild generated native stages on the new computer. Old
   compiled stages/receipts can contain machine paths and are not a portable SDK.
2. Install/copy the pinned Windows tools: x86_64 CPython **3.12.10**, the existing
   MSYS2 toolchain, CMake **4.3.0**, Ninja **1.13.2**, Java **21**, Android SDK with
   platform **35**, build-tools **34.0.0**, NDK **26.3.11579264**, and Gradle **8.9**
   offline inputs. Versions remain pinned in the existing manifests; `.env`
   selects locations, not arbitrary replacement dependency versions.
3. Run this once in **each** project, then edit its `.env` locally:

   ```powershell
   .\dev.ps1 configure
   notepad .env
   ```

   `configure` refuses to replace an existing file. For a legacy `.env`, preserve
   a private backup outside Git and explicitly compare/migrate `.env.example`.
   Do not send `.env`, keys, credentials, or a private backup in console reports.
4. Set the same `WESNOTH_SERVER_IP` in both files: the Windows LAN IPv4 address
   reachable from LDPlayer. Update Python/MSYS/CMake and Android/Java/cache/data
   paths. Paths may contain spaces, use forward slashes, and are relative to
   their own project unless absolute. `${PROJECT_ROOT}`, `${WORKSPACE_ROOT}`,
   `${WESNOTH_...}` and `%LOCALAPPDATA%`/`%USERPROFILE%`/`%ProgramFiles%` references
   expand as data. Quotes enclose literal values; no shell evaluation, `export`,
   inline comments, duplicate/unknown keys or unrecognized environment formats.
5. Privately transfer the **original Windows** `debug.keystore`, the directory
   directly containing it, and an original signed Windows base APK. Select them
   with client `WESNOTH_ANDROID_USER_HOME` and `WESNOTH_SIGNER_REFERENCE_APK`.
   The VPS test signer is different. Gradle must retain the Windows key; missing
   keys and differing APK signers stop the pipeline. Transfer the pinned 23
   archives into `WESNOTH_ARCHIVE_DIRECTORY`, the game-data source into
   `WESNOTH_GAME_DATA_ROOT`, and the offline Gradle cache to its selected path.
   Boost/network's original fixed cache is populated only with verified missing
   archives; occupied differing files are preserved. ICU/layout preparation uses
   their existing project-owned source caches.

With internet available, prepare the selected caches explicitly:

```powershell
# server project
.\dev.ps1 prepare -Download
.\dev.ps1 install
# client project (Android command-line tools/sdkmanager must already be installed)
.\dev.ps1 prepare -Download
```

Server `prepare` without `-Download` verifies its cached artifacts offline.
Client `prepare` requires `-Download`; use `check` for offline verification.
These wrap the existing pinned preparation tools; they do not install a general
Windows/MSYS2/Java/Python toolchain or upgrade packages. Retain the established
MSYS2 packages and cached source archives from the old workstation. Server
`WESNOTH_SERVICE_ENV_ROOT`, `WESNOTH_MONGODB_ROOT` and
`WESNOTH_DEPENDENCY_CACHE` select managed dependency locations. Their ownership
and receipt checks still apply. Install them on the new computer, then build:

```powershell
# server
.\dev.ps1 build
```

## Move existing accounts and identity

MongoDB runs **locally**. The server `.env` exposes loopback host, port, dedicated
`wesnoth_...` database name and replica-set name. Defaults remain
`127.0.0.1:27018`, `wesnoth_game`, `wesnoth-rs`. Credentials, sessions and generated
secrets remain in the private owned runtime, selected by `WESNOTH_RUNTIME_ROOT`.
The authenticated URI is generated/retained there, not bundled into the client.

For the current runtime-v3, keep the saved Mongo settings. Editing `.env` does
not rename a database/replica set or silently rewrite an existing runtime.
Configuration conflicts fail before startup. HTTP 18765 and protocol ports
15000/15001/15002 remain release constants. MongoDB stays bound to loopback.

Use the existing cold backup workflow with all five services cleanly stopped,
then privately transfer the **whole verified backup directory**. For example:

```powershell
# old computer, server project; after configuring .env for its existing runtime
.\dev.ps1 backup -DestinationPath E:\PrivateTransfer\runtime-v3-backup
# new computer, server project; .env runtime must be a NEW destination
.\dev.ps1 restore -BackupPath E:\PrivateTransfer\runtime-v3-backup -PreviousRuntimeRoot C:\Users\OldUser\AppData\Local\WesnothAlliance\runtime-v3
```

Use the real original runtime path for `-PreviousRuntimeRoot`; the old directory
need not exist on the new host. Restore rebases only the copied runtime, verifies
its supported schema and authenticated database, and retains the archive/original.
It does not carry the separately located TLS identity or Android saved profiles.
Privately copy the original transport identity too when retaining its address.
Select its directory in server `WESNOTH_IDENTITY_ROOT` and its public-profile.json
in client `WESNOTH_PUBLIC_PROFILE_PATH`. The public profile contains endpoint and
certificate only; server private keys/credentials stay on the server.

For a different LAN address, select a **new empty identity directory**, set the
server `.env` IP, and run server `dev.ps1 identity`. Existing mismatched identities
are refused and keys never replaced. Point the client `.env` to the matching
public profile and IP, then rebuild. Any saved device trust/profile transition
requires the existing explicit reviewed migration process; editing IP alone does
not override certificate pinning or replace a trusted profile.

Only for an intentionally **empty new development game**, select a separate new
runtime and use `dev.ps1 init -NewDevelopmentRuntime`. This creates Court schema5
and privately prompts for the new administrator. It is not the account-transfer
step. An existing directory is refused unless its interrupted initialization was
reviewed and `-ResumeInitialization` is explicitly added.

## Daily checks and evidence

Run server `dev.ps1 check`, then `dev.ps1 start`; require
`W07 UNIFIED GAME SERVICES READY`. Run client `dev.ps1 check`, then
`dev.ps1 build` (or `build -Update` for a reviewed existing account update).
Verify the reported original signer before installation. Client `dev.ps1 install`
uses the existing **in-place** `-KeepSavedProfile` installer for an already
prepared LDPlayer/device. Initial emulator/application/OBB setup is separate.
Keep the current installed game, saved accounts/campaigns and trusted profile.

Top-level and child tools print unique `diagnostics` log/report paths. `init`
intentionally has no transcript because it collects private administrator input.
Keep failed logs and stop at the first unexpected result. Settings are scoped to
child processes and restored in the calling shell. The Android input derived from
`.env` contains only the resolved public profile path, not other workstation or
private database configuration.

This configuration work does not establish new Windows build/gameplay acceptance.
Android1192629/protocol5/schema5/backend-worker1192626 stay current; the prior
F1–F7 manual feedback checkpoint remains pending. Verification evidence and its
Linux/Windows limits are recorded separately in `WINDOWS_DEVELOPMENT_VERIFICATION.json`.
