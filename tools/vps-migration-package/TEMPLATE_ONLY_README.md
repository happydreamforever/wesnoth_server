# Public migration package templates

These files are the public authored sources for the private VPS development transfer. Their directory layout matches the completed transfer ZIP. They are not a self-contained runtime or archive: Git bundles, exact data/asset payloads, dependency archives, Android signing key, test TLS private key, APKs and the generated manifest/checksums are intentionally excluded from Git.

Do not run restore.py or environment commands directly in this template checkout. Use the completed private ZIP, verify its adjacent SHA256 file, then follow its START_HERE.md. Its generated migration/MANIFEST.json covers the complete payload; environment/SHA256SUMS also covers omitted vendor inputs. Those generated files are included only when assembling the private transfer. Current transfer HEADs are recorded in migration/git/repositories.json, so commit hashes are not embedded self-referentially in these templates.

The development workspace retains unrelated README modifications and previous server documentation additions. Stage only reviewed delivery changes. Never publish the private transfer or its keys. Reinstall the environment and verify new builds before claiming new-VPS acceptance.

The original packaging verification passed complete ZIP extraction, both Git histories and exact dirty edits,26748 game-data files, repeated verification and deliberate tamper rejection. The environment smoke runner passed122 tests using the old VPS images/Python; rebuilding all images and Android from scratch is still a separate acceptance gate.
