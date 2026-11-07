# Continue on the existing Windows computer first

The current target is **D:\Test\wesnoth-setup**. Adopt and verify the development
`.env` commands in its existing `wesnoth_server` and `wesnoth_client` checkouts.
Moving to another computer is a later step.

The configuration work belongs on **feature/windows-dev-env** in both GitHub
repositories. Published `main` stays at the accepted baseline. Confirm the remote
feature branch exists and matches the delivered commit before fetching it on
Windows. A local commit or failed push does not establish publication.

## First Windows batch: inspect the existing checkouts

Run in PowerShell on the current computer:

```powershell
$root = 'D:\Test\wesnoth-setup'
git -C "$root\wesnoth_server" status --short --branch
git -C "$root\wesnoth_server" log -1 --oneline
git -C "$root\wesnoth_client" status --short --branch
git -C "$root\wesnoth_client" log -1 --oneline
```

Return this complete console output. Stop this batch there. These commands only
inspect Git state; existing services and LDPlayer can stay open. Review local
edits and the current branches before switching either checkout.

## After review and verified feature-branch publication

Fetch the feature branch into each existing checkout, then switch to its local
tracking branch. Use a normal fetch/switch; retain local edits and stop if Git
reports a conflict. Main is not merged, reset or pushed as part of this work.
For the first switch, after status review:

```powershell
$root = 'D:\Test\wesnoth-setup'
git -C "$root\wesnoth_server" fetch origin refs/heads/feature/windows-dev-env:refs/remotes/origin/feature/windows-dev-env
git -C "$root\wesnoth_server" switch --track -c feature/windows-dev-env origin/feature/windows-dev-env
git -C "$root\wesnoth_client" fetch origin refs/heads/feature/windows-dev-env:refs/remotes/origin/feature/windows-dev-env
git -C "$root\wesnoth_client" switch --track -c feature/windows-dev-env origin/feature/windows-dev-env
```

If a local feature branch already exists, inspect it and use it instead of
creating it again. Verify both resulting commit IDs against the delivery.

## Adopt each project's .env in place

Review the current private `.env` locally against `.env.example`; retain a private
backup outside Git before editing a legacy file. `dev.ps1 configure` creates only
a missing `.env` and deliberately refuses to replace an existing one. Keep all
private values out of returned console output.

Use the existing paths and saved configuration:

- Workspace: `D:/Test/wesnoth-setup`; MSYS2: `D:/Test/wesnoth-setup/msys64`.
- Server runtime: `%LOCALAPPDATA%/WesnothAlliance/runtime-v3`, with its saved
  MongoDB endpoint/name/replica set and credentials. The previously accepted
  defaults were `127.0.0.1:27018`, `wesnoth_game`, `wesnoth-rs`.
- Existing transport identity and public profile, retaining their pinned address.
  The last accepted Windows address was `100.99.99.14`; verify the current saved
  address locally. The template's `192.168.1.10` is illustrative.
- Existing Python3.12.10, service environment, MongoDB installation, CMake,
  Ninja, Android SDK, Java, Gradle/source caches and game-data locations.
- Existing original Windows `debug.keystore` in place, plus a retained original
  signed Windows base APK as the signer reference. The separate VPS fixture
  signer is not the Windows signer.

The first executable `.env` checks, after reviewing the settings, are:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Test\wesnoth-setup\wesnoth_server\dev.ps1 check
powershell.exe -NoProfile -ExecutionPolicy Bypass -File D:\Test\wesnoth-setup\wesnoth_client\dev.ps1 check
```

Return both consoles and their printed diagnostic paths. Resolve the first
unexpected result before proceeding. Preparation/install/rebuild is needed only
if a reviewed check establishes it; current verified inputs and builds remain
available. This phase uses the existing runtime and identity.

After accepting the checks, server `dev.ps1 start` uses the existing W01-W07
workflow to verify/reuse healthy services and start missing ones. APK changes
use the established preserving build/install workflow when required. The prior
Android1192629/protocol5/schema5/backend-worker1192626 and F1-F7 acceptance status
remain in force. Actual Windows execution of the new wrappers is still pending.

When this computer's configuration is accepted, use
`WINDOWS_DEVELOPMENT_ENVIRONMENT.md` for the later computer migration, including
verified private backup/identity/signer transfer and dependency setup.
