# Windows native transport accepted; next milestone is Android execution

Both returned files `alliance-native-20261019-213954-440-8912eeea6d884f23a2a3ff882192259c.txt` and `.json` confirm all 24 native transport cases passed. The existing Windows executable was reused; no compilation occurred. The user explicitly confirms internet/WAN was disconnected while local Ethernet remained connected. This is user-observed offline operation, not an independent network trace.

## Completed scope

- The existing public profile and disconnected-send guards pass.
- TLS1.2 and TLS1.3 echo the exact 66-byte test frame; unsolicited server-push receives a 66-byte gzip-prefixed frame without sending client application bytes.
- Incorrect IP/pin, invalid addresses, expired/untrusted certificates, plaintext and downgrade attempts are rejected as expected.
- Cancellation, deadlines, frame limits and truncated responses produce the expected errors. Each socket case uses one connection and the required TLS preamble.

Expected negative-case errors in the JSON are successful rejection checks. For example, the untrusted peer's TLSV1_ALERT_UNKNOWN_CA is expected; it is not a new failure.

## Current Windows action

No command is needed for this acceptance checkpoint. Keep the existing executable, old and new fixture directories, diagnostics, original TLS identity, installed game, OBB and completed dependency stages. Do not rerun the passed fixture or initialize MongoDB for this report review. The documentation updates can be pulled with the next implementation delivery.

## Next development and test delivery

The next milestone is to build and execute the Android version of this transport component in LDPlayer. Prepare a small independent test using the existing Android x86_64/API23 NDK, Boost1.88/OpenSSL3.4.1 prefixes and selected LDPlayer API28 instance. Preserve completed engine/library/APK stages. Supply and verify the exact Windows build/test commands before asking the user to run them; that Android handoff has not been delivered yet.

The earlier VPS Android cross-build confirms compilation only. Current Windows loopback success does not establish Android transport execution, account login, native backend bridge integration, MongoDB startup or Alliance gameplay. Those remain explicit checklist items. No physical-phone test or repeated environment inventory is requested.
