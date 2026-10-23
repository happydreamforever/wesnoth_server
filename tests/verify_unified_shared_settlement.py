"""Verify production captain settlement of an existing disposable native run.

No credentials or tokens are printed. The fixture owns a fresh MongoDB on27019
inside the network-disabled verification container; no game runtime is read.
"""
import argparse
import json
import sys
import time
from pathlib import Path
from pymongo import MongoClient
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from alliance.domain import AllianceService
from alliance.rules import LEADER_REWARDS, TEAM_REWARDS

parser = argparse.ArgumentParser()
parser.add_argument('--fixture', type=Path, required=True)
args = parser.parse_args()
f = json.loads(args.fixture.read_text())
assert f['purpose'] == 'disposable-shared-engine-fixture'
assert f['database'].startswith('alliance_test_shared_engine_')
client = MongoClient('mongodb://127.0.0.1:27019/?replicaSet=shared_fixture', tz_aware=True)
db = client[f['database']]
domain = AllianceService(db)
run_id = f['run_id']
before = {a['account_id']: domain.get_account(a['account_id']) for a in f['players']}
review = domain.shared_result_review(f['players'][0]['account_id'], run_id)
assert review['review_state'] in ('awaiting_captains', 'settled'), review
if review['review_state'] == 'awaiting_captains':
    assert all(next(h for h in row['heroes'] if h['hero_id'] == 'konrad')['total_experience'] == 27 for row in before.values())
    for index in f['captain_indices']:
        domain.shared_confirm_result(f['players'][index]['account_id'], run_id, review['candidate_digest'])
for _ in range(200):
    run = domain.get_run(run_id)
    if run['state'] == 'completed':
        break
    time.sleep(.1)
else:
    raise RuntimeError('Settlement timed out')
receipt = db.settlements.find_one({'_id': run_id})
assert receipt and len(receipt['rewards']['players']) == f['size'] * 2
assert db.settlements.count_documents({'_id': run_id}) == 1
assert domain.shared_finish(run_id, f['generation']) == receipt
assert domain.shared_finish(run_id, f['generation']) == receipt
records = []
for actor in f['players']:
    account = domain.get_account(actor['account_id'])
    participant = next(p for p in run['participants'] if p['account_id'] == actor['account_id'])
    outcome = 'draw' if receipt['result']['draw'] else 'win' if participant['team_id'] == receipt['result']['winner_team_id'] else 'loss'
    expected = LEADER_REWARDS[outcome]
    selected = next(h for h in account['heroes'] if h['hero_id'] == 'konrad')
    assert selected['total_experience'] == 27 + expected
    assert selected['revision'] == 2
    others = [h for h in account['heroes'] if h['hero_id'] != 'konrad']
    assert all(h['total_experience'] == 27 and h['revision'] == 1 for h in others)
    assert others == [h for h in before[actor['account_id']]['heroes'] if h['hero_id'] != 'konrad']
    assert db.accounts.find_one({'_id': actor['account_id']})['active_run_id'] is None
    records.append({'side': actor['side'], 'selected_hero': 'konrad', 'xp_awarded': expected,
                    'total_experience': selected['total_experience'], 'unchanged_other_heroes': len(others)})
for team_id in f['teams']:
    team = domain.get_team(f['players'][0]['account_id'], team_id)
    outcome = 'draw' if receipt['result']['draw'] else 'win' if team_id == receipt['result']['winner_team_id'] else 'loss'
    assert team['experience'] == TEAM_REWARDS[outcome] and team['active_run_id'] is None
catalogue_hashes = sorted(db.game_runs.distinct('catalog_sha256', {'kind': 'campaign'}))
assert len(catalogue_hashes) == 1
result = {'status': 'passed', 'catalog_sha256': catalogue_hashes[0], 'size': f['size'], 'native_reports_and_two_captain_agreements': True,
          'exactly_once_settlement_and_release': True, 'selected_hero_rewards': records,
          'draw': receipt['result']['draw'], 'rating_total': sum(domain.get_team(f['players'][0]['account_id'], t)['rating'] for t in f['teams'])}
assert result['rating_total'] == 2000
(args.fixture.parent / 'settlement-validation.json').write_text(json.dumps(result, indent=2) + '\n')
print('PASS actual native END reports, both captain approvals, selected-hero XP, team XP/rating and exactly-once settlement', flush=True)
client.close()
