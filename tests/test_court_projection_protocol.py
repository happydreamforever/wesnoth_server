"""Real Court projections through both compiled native response validators.

Run with a disposable loopback replica set, a C++17 compiler and the pinned
Boost headers. This does not open a game runtime or exercise Android input.
"""
from copy import deepcopy
import json
import os
from pathlib import Path
import subprocess
import tempfile
import unittest
from uuid import uuid4

import test_court_battles as battle_fixture
from alliance.court.geography import catalogue


ROOT = Path(__file__).resolve().parents[1]
CLIENT = ROOT.parent / 'wesnoth_client'


@unittest.skipUnless(os.environ.get('ALLIANCE_TEST_MONGO_URI'), 'Requires disposable loopback replica set')
class CourtProjectionProtocol(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        battle_fixture.CourtBattles.setUpClass()
        cls.directory = tempfile.TemporaryDirectory(prefix='court-projection-protocol-')
        cls.addClassCleanup(cls.directory.cleanup)
        cls.addClassCleanup(battle_fixture.CourtBattles.tearDownClass)
        boost = Path(os.environ.get('ALLIANCE_TEST_BOOST_INCLUDE',
                                    CLIENT / 'build/android-boost/prefix/include'))
        cls.probes = {}
        for name, headers in (('bridge', ROOT / 'alliance_bridge'),
                              ('client', CLIENT / 'alliance_native')):
            executable = Path(cls.directory.name) / name
            subprocess.run([os.environ.get('CXX', 'c++'), '-std=c++17', '-O0', '-g0',
                '-I' + str(headers), '-I' + str(boost),
                str(ROOT / 'tests/court_projection_protocol_check.cpp'), '-o', str(executable)],
                check=True, timeout=120)
            cls.probes[name] = executable

    def setUp(self):
        self.fixture = battle_fixture.CourtBattles()
        self.fixture.setUp()
        self.addCleanup(self.fixture.tearDown)
        # The battle fixture intentionally has minimal geography. Entry uses
        # the real 128-Area catalogue fields, including realm labels.
        for area in catalogue()['areas']:
            self.fixture.db.court_areas.update_one({'_id': area['id']}, {'$set': {
                'name': area['name'], 'number': area['number'],
                'realm_id': area['realm_id'], 'realm_name': area['realm_name'],
                'enabled': area['id'] == 'A001', 'mode': 'auto',
                'team_count': 2 if area['id'] == 'A001' else 0, 'revision': 0}}, upsert=True)

    def query(self, query, actor=None, **payload):
        return self.fixture.domain.court_query(actor or self.fixture.a,
            {'version': 1, 'query': query, 'payload': payload})

    def assert_native(self, document, *, accepted=True):
        encoded = json.dumps(document, ensure_ascii=False, separators=(',', ':'))
        for name, executable in self.probes.items():
            with self.subTest(native_validator=name):
                result = subprocess.run([str(executable)], input=encoded, text=True,
                                        capture_output=True, timeout=10)
                self.assertEqual(result.returncode, 0 if accepted else 1, result.stdout + result.stderr)
                self.assertEqual(result.stdout.strip(),
                    'COURT PROJECTION ACCEPTED' if accepted else 'COURT PROJECTION REJECTED')

    def test_fresh_team_entry_with_no_team_or_heroes(self):
        actor = self.fixture.player()
        self.fixture.db.account_heroes.delete_many({'account_id': actor})
        snapshot = self.query('snapshot', actor)
        self.assertIsNone(snapshot['data']['team'])
        self.assertEqual(snapshot['data']['heroes'], [])
        self.assertEqual(len(snapshot['data']['areas']), 128)
        for query in ('snapshot', 'areas', 'my_team'):
            self.assert_native(self.query(query, actor))

    def test_member_entry_with_ten_members_and_every_hero_form(self):
        f = self.fixture
        members = [{'account_id': f.a, 'joined_at': f.now}]
        for _ in range(9):
            members.append({'account_id': f.player(), 'joined_at': f.now})
        f.db.court_teams.update_one({'_id': f.ta}, {'$set': {'members': members}})
        f.db.account_heroes.delete_many({'account_id': f.a})
        for hero in f.catalog['heroes']:
            forms = [row['id'] for row in f.catalog['forms'] if row['hero_id'] == hero['id']]
            f.db.account_heroes.insert_one({'_id': str(uuid4()), 'account_id': f.a,
                'hero_id': hero['id'], 'forms': forms, 'total_experience': 64, 'revision': 0})
        snapshot = self.query('snapshot')
        self.assertEqual(len(snapshot['data']['team']['members']), 10)
        self.assertEqual(len(snapshot['data']['heroes']), 117)
        for query in ('snapshot', 'areas', 'my_team'):
            self.assert_native(self.query(query))
        self.assert_native(self.query('area', area_id='A001'))

    def test_reopened_cancelled_castle_and_saved_views(self):
        f = self.fixture
        run = f.attack()
        f.command(f.admin, 'admin_cancel_match', match_id=run,
                  reason='Disposable native projection regression')
        for query, payload in (('snapshot', {}), ('areas', {}), ('my_team', {}),
                               ('castle', {'castle_id': 'A001-C001'}),
                               ('plans', {}), ('plan', {'match_id': run}), ('history', {})):
            with self.subTest(query=query):
                self.assert_native(self.query(query, **payload))

    def test_captain_entry_excludes_departed_member_allowances(self):
        f = self.fixture
        allowances = {str(uuid4()): 7 for _ in range(70)}
        allowances[f.a] = 13
        f.db.court_teams.update_one({'_id': f.ta}, {'$set': {'allowances': allowances}})
        before = f.db.court_teams.find_one({'_id': f.ta})
        for query in ('snapshot', 'my_team'):
            document = self.query(query)
            self.assert_native(document)
            self.assertEqual(document['data']['team']['allowances'], {f.a: 13})
        self.assert_native(self.query('area', area_id='A001'))
        self.assertEqual(f.db.court_teams.find_one({'_id': f.ta}), before)

    def test_reopened_completed_castle_and_saved_views(self):
        f = self.fixture
        run = f.attack()
        f.finish(f.load(run))
        for query, payload in (('snapshot', {}), ('my_team', {}),
                               ('castle', {'castle_id': 'A001-C001'}),
                               ('plans', {}), ('plan', {'match_id': run}), ('history', {})):
            with self.subTest(query=query):
                self.assert_native(self.query(query, **payload))

    def test_pending_journal_can_read_legacy_receipt_without_changing_it(self):
        f = self.fixture
        run, command_id = f.attack(), str(uuid4())
        request = {'version': 1, 'operation': 'cancel_attack', 'payload': {
            'command_id': command_id, 'match_id': run,
            'expected_revision': f.match(run)['revision']}}
        original = f.domain.court_command(f.a, request)
        legacy = deepcopy(original)
        legacy['data']['match']['description'] = (
            'Cancelled by a participant.\nNo rewards or Castle ownership change.')
        key = f.generation + ':' + f.a + ':' + command_id
        f.db.court_commands.update_one({'_id': key}, {'$set': {'result': legacy}})
        self.assert_native(self.query('command_status', command_id=command_id))
        self.assert_native(f.domain.court_command(f.a, request))
        self.assertEqual(f.db.court_commands.find_one({'_id': key})['result'], legacy)

    def test_control_characters_still_rejected(self):
        document = self.query('snapshot')
        for bad in ('first\nsecond', 'first\tsecond', 'first\rsecond', 'first\x00second'):
            invalid = deepcopy(document)
            invalid['data']['description'] = bad
            with self.subTest(control=repr(bad)):
                self.assert_native(invalid, accepted=False)


if __name__ == '__main__':
    unittest.main()
