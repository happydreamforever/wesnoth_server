"""Resume the one reviewed account-client compilation failure in place."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

from tools.build_alliance_bridge import BuildError
from tools import world_worker_recovery as recovery
from tools import world_worker_resource_recovery as resource
from tools import world_worker_ninja_recovery as ninja

PURPOSE = 'wesnoth-world-worker-account-source-recovery'
INPUT = 'wesnoth_server/tools/world_worker_account_recovery.py'
ACCOUNT_INPUT = 'wesnoth_client/alliance_native/account_client.cpp'
LEGACY_BUILDERS = frozenset({
    'ca3bd66aa658734a26196cfa4007433a91ca074c4c4101619247a21712875172',
    '07bc74a907c3302a31011cec6eb17f67931100bec169d04b42ffbc5fea38efd1',
})
# The exact reviewed account-profile reader, with matching checkout line endings.
ACCOUNT_REVISIONS = {
    '5a3fa0ea86560ae5c4d6a9f1511ed3f5b9f0cdc970987f512f9493e68ff3d53e': '52eca5ebd33bc3964b9233f4f51cf4843b29e2967b92a8b1bb26d70bcfb52a79',
    '2ce65b62a263734e9633d6eb5d5773a18efb55774b5a813b91ccf0395463f733': '2536c4259171d31baa3588fda2bd5ee7da1eeb0968d80216bd7c5dc9f2272f0d',
}
NINJA_HELPERS = frozenset({
    'df6888cc7ac006b6b8d5ef06e2c42be88089f86c2d960c1b5ecfa178f86f6d2c',
    'f1bc54cafcab11f7f7c138565b63ef70c05c2ae269ebca44ba3bcbe8ccec207d',
})


def _paths(stage):
    stage = recovery._path(stage)
    recovery._path(stage.parent, directory=True)
    if stage.exists():
        recovery._path(stage, directory=True)
    return (stage, stage.with_name(stage.name + '.account-recovery.json'),
            stage.with_name(stage.name + '.account-recovery-complete.json'),
            stage.with_name(stage.name + '.account-recovery.lock'))


def _legacy(owner, expected):
    recovery._binding(owner)
    recovery._binding(expected)
    prior, current = owner['inputs'], expected['inputs']
    changed = {recovery.BUILDER_INPUT, ACCOUNT_INPUT}
    if (INPUT not in current or INPUT in prior or set(prior) != set(current) - {INPUT}
            or prior.get(recovery.BUILDER_INPUT) not in LEGACY_BUILDERS
            or prior.get(ninja.INPUT) not in NINJA_HELPERS
            or not ACCOUNT_REVISIONS.get(prior.get(ACCOUNT_INPUT))
            or current.get(ACCOUNT_INPUT) != ACCOUNT_REVISIONS.get(prior.get(ACCOUNT_INPUT))
            or any(value != current[name] for name, value in prior.items() if name not in changed)):
        raise BuildError('Only the reviewed account-client worker source revision may resume in place.')


def _history(stage):
    """Validate completed provenance; keep all prior recovery files immutable."""
    if recovery.recovery_pending(stage) or resource.resource_recovery_pending(stage) or ninja.pending(stage):
        raise BuildError('Earlier worker recovery is incomplete; preserve its journals.')
    if ninja.configure_pending(stage):
        raise BuildError('Restore the pending Ninja configuration before account-source recovery.')
    paths = []
    for suffix in ('.sysroot-recovery.json', '.sysroot-recovery-complete.json',
                   '.resource-recovery.json', '.resource-recovery-complete.json',
                   '.ninja-recovery.json', '.ninja-recovery-complete.json'):
        path = recovery._path(stage.with_name(stage.name + suffix))
        if path.exists():
            paths.append(path)
    # Guard backup files and their receipts are retained too. Completed guard
    # inventory concerns only its backups, never the newer live Ninja history.
    for directory in sorted(stage.parent.glob(stage.name + '.ninja-configure-*')):
        recovery._path(directory, directory=True)
        paths.extend(sorted(path for path in directory.iterdir() if path.is_file()))
        if any(path.is_dir() for path in directory.iterdir()):
            raise BuildError('Unexpected nested Ninja guard files; preserved.')
    return {path.relative_to(stage.parent).as_posix(): ninja._row(path) for path in paths}


def _completed_ninja(stage, owner, inventory):
    _, journal, complete = ninja._paths(stage)
    if not journal.exists() or not complete.exists():
        raise BuildError('The reviewed Ninja recovery must be complete before source continuation.')
    record = ninja._intent(journal, stage, owner)
    if recovery._read_json(complete) != ninja._completion(record):
        raise BuildError('The reviewed Ninja completion differs; preserved.')
    resource_path = stage.with_name(stage.name + '.resource-recovery.json')
    if hashlib.sha256(ninja._raw(resource_path)).hexdigest() != record['resource_journal_sha256']:
        raise BuildError('Original resource provenance changed; preserved.')
    original = record['inventory']['files']
    restat = 'engine/.ninja_log.restat'
    if inventory['files'].get(restat) != original.get(restat):
        raise BuildError('The original reviewed Ninja temporary changed; preserved.')
    output_names = ['engine/' + name for name in ninja._log_outputs(ninja._raw(stage / restat))]
    if any(name not in original or inventory['files'].get(name) != original[name] for name in output_names):
        raise BuildError('A previously retained compiled output changed; preserved.')
    for name in ('engine/.ninja_log', 'engine/.ninja_deps'):
        if not inventory['files'].get(name, {}).get('bytes'):
            raise BuildError('Current incremental Ninja history is missing; preserved.')


def _record(path, stage, expected=None):
    record = recovery._read_json(path)
    if (not isinstance(record, dict) or set(record) != {'format', 'purpose', 'stage', 'original_owner',
            'original_owner_hex', 'expected_binding', 'inventory', 'history'}
            or type(record['format']) is not int or record['format'] != 1
            or record['purpose'] != PURPOSE or record['stage'] != str(stage)
            or not isinstance(record['original_owner_hex'], str) or not isinstance(record['history'], dict)):
        raise BuildError('Account-source recovery journal is invalid; preserved.')
    _legacy(record['original_owner'], record['expected_binding'])
    if expected is not None and expected != record['expected_binding']:
        raise BuildError('Account-source recovery belongs to different inputs; preserved.')
    resource._inventory_record(record['inventory'])
    resource._inventory_record({'files': {'owner.json': record['inventory']['files']['owner.json'],
                                         **record['history']}, 'directories': []})
    for name in record['history']:
        if not (name.startswith(stage.name + '.') and resource._relative(name)):
            raise BuildError('Account-source history path is invalid; preserved.')
    try:
        raw = bytes.fromhex(record['original_owner_hex'])
        row = record['inventory']['files']['owner.json']
        if (json.loads(raw) != record['original_owner'] or len(raw) != row['bytes']
                or hashlib.sha256(raw).hexdigest() != row['sha256']):
            raise ValueError
    except (ValueError, TypeError):
        raise BuildError('Account-source original ownership differs; preserved.') from None
    return record


def _completion(record):
    return {'format': 1, 'purpose': PURPOSE, 'journal_sha256': recovery._hash(record),
            'status': 'account_source_binding_updated_not_verified_build'}


def account_recovery_pending(stage):
    stage, journal, complete, _ = _paths(stage)
    if not journal.exists():
        if complete.exists():
            raise BuildError('Account-source completion has no journal; preserved.')
        return False
    record = _record(journal, stage)
    if complete.exists():
        if recovery._read_json(complete) != _completion(record):
            raise BuildError('Account-source recovery completion differs; preserved.')
        return False
    recovery._path(stage, directory=True)
    return True


def _unchanged(stage, record):
    actual = recovery._inventory(stage)
    actual['files'].pop('owner.json', None)
    expected = {'directories': record['inventory']['directories'],
                'files': {name: row for name, row in record['inventory']['files'].items() if name != 'owner.json'}}
    if actual != expected or _history(stage) != record['history']:
        raise BuildError('Worker files or prior recovery records changed during account-source continuation; preserved.')


def resume_account_stage(stage, expected_binding, validate_stage):
    """Change only owner.json; compile directly from the corrected client file."""
    stage, journal, complete, lock = _paths(stage)
    recovery._path(stage, directory=True)
    recovery._binding(expected_binding)
    with resource._lock(lock):
        owner_path = stage / 'owner.json'
        owner = recovery._read_json(owner_path)
        if complete.exists() and not journal.exists():
            raise BuildError('Account-source completion has no journal; preserved.')
        new_intent = not journal.exists()
        if new_intent:
            if owner == expected_binding:
                return False
            _legacy(owner, expected_binding)
            if (stage / 'receipt.json').exists():
                raise BuildError('Completed workers cannot use incomplete account-source recovery; preserved.')
            inventory = recovery._inventory(stage)
            history = _history(stage)
            _completed_ninja(stage, owner, inventory)
            validate_stage()
            if recovery._inventory(stage) != inventory or _history(stage) != history:
                raise BuildError('Worker files changed during source validation; preserved.')
            record = {'format': 1, 'purpose': PURPOSE, 'stage': str(stage), 'original_owner': owner,
                      'original_owner_hex': ninja._raw(owner_path).hex(), 'expected_binding': expected_binding,
                      'inventory': inventory, 'history': history}
            recovery._publish(journal, record)
            record = _record(journal, stage, expected_binding)
        else:
            record = _record(journal, stage, expected_binding)
            if complete.exists():
                if (recovery._read_json(complete) != _completion(record) or owner != expected_binding
                        or ninja._raw(owner_path) != resource._new_owner(expected_binding)):
                    raise BuildError('Account-source recovery completion or ownership differs; preserved.')
                return True
        if (stage / 'receipt.json').exists():
            raise BuildError('Completed workers cannot resume pending account-source recovery; preserved.')
        raw = ninja._raw(owner_path)
        if raw not in (bytes.fromhex(record['original_owner_hex']), resource._new_owner(expected_binding)):
            raise BuildError('Account-source recovery ownership changed; preserved.')
        if not new_intent:
            _unchanged(stage, record)
            validate_stage()
        _unchanged(stage, record)
        if ninja._raw(owner_path) != raw:
            raise BuildError('Account-source ownership changed before publication; preserved.')
        if raw != resource._new_owner(expected_binding):
            resource._replace_owner(stage, resource._new_owner(expected_binding))
        if ninja._raw(owner_path) != resource._new_owner(expected_binding):
            raise BuildError('Account-source ownership update differs; preserved.')
        _unchanged(stage, record)
        recovery._publish(complete, _completion(record))
        return True
