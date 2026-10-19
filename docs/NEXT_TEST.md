# Next step: independent VPS account-transport work

On 2026-10-20 the user said "I can't delete it. Let's ignore it." Malware troubleshooting is deferred at the user's request. No further scan, removal command or repeated quarantine question is requested. The removal method/error was not supplied: this does not establish a failed Defender quarantine operation. The last supplied alert was Severe/Active on 2026-10-19 for C:\Windows\SysWOW64\netactive32.dll; cleanup and current network status are unconfirmed. Its relationship to the traced process or MongoDB crash remains unverified.

## Current Windows state

The earlier MongoDB startup failed with a Windows file-sharing violation. Setting aside the security investigation does not resolve that technical failure or validate database initialization. Keep initialization, admin login, persistence and disconnected-WAN Alliance checks pending. Preserve the partial runtime, completed game, caches, native stages and reports. No pull, rebuild, reinstall, database retry or additional diagnostic collection is required for this documentation handoff.

The recommendation remains to resolve the active detection before entrusting this Windows installation with new credentials or database records. This is risk advice, not a prerequisite for independent VPS development. Do not disable protection or add exclusions to work around the issue. The existing .env internet database is not an offline replacement and remains unused.

## Next independent implementation scope

A read-only source review confirms that the current client's network_asio.cpp disables TLS for numeric addresses and supports plaintext fallback. The server's server_base.cpp already supports configured TLS certificates/private keys. Neither finding means that custom account integration is implemented.

Continue checklist section 3 on the VPS:

- Provision a public connection/trust profile for an explicit Alliance account connection mode; private server keys must never reach the Android client.
- Verify the server identity for a numeric LAN IP and reject downgrade replies, EOF fallback and invalid handshakes in that account mode.
- Do not transmit account passwords or session tokens until the provisioned profile has authenticated the server.
- Preserve the existing guest connection behavior and previously completed game stages.
- Verify trusted identity, untrusted/wrong/expired identity, downgrade/EOF failure, invalid handshake and guest compatibility with isolated VPS fixtures.

This turn records scope and completes source review only; no transport code or runtime test was changed. A later tested implementation delivery will provide its own exact Windows build/run/test commands. Windows MongoDB acceptance remains separate and pending; do not label Alliance playable or persistently tested on Windows from VPS results alone.
