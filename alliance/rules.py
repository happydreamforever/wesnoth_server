"""Versioned Alliance rules. Values are from the supplied Wesnoth 1.19.26 data.

This module contains no combat simulator. Only the trusted game bridge may report
completed matches; it cannot choose reward amounts or arbitrary leader stats.
"""
from __future__ import annotations

from copy import deepcopy
import math

RULESET_VERSION = 'alliance-v1'
TEAM_CAPACITY = 8
MAX_JOIN_REQUESTS = 64

# (level, experience needed, permitted advancement types). Terminal AMLA disabled.
UNIT_TYPES = {
    'Spearman': (1, 42, ('Swordsman', 'Pikeman', 'Javelineer')),
    'Swordsman': (2, 80, ('Royal Guard',)),
    'Pikeman': (2, 69, ('Halberdier',)),
    'Javelineer': (2, 100, ()),
    'Royal Guard': (3, 150, ()),
    'Halberdier': (3, 150, ()),
    'Elvish Fighter': (1, 37, ('Elvish Captain', 'Elvish Hero')),
    'Elvish Captain': (2, 85, ('Elvish Marshal',)),
    'Elvish Hero': (2, 80, ('Elvish Champion',)),
    'Elvish Marshal': (3, 150, ()),
    'Elvish Champion': (3, 150, ()),
    'Orcish Grunt': (1, 42, ('Orcish Warrior',)),
    'Orcish Warrior': (2, 67, ('Orcish Warlord',)),
    'Orcish Warlord': (3, 150, ()),
    'Dwarvish Fighter': (1, 45, ('Dwarvish Steelclad',)),
    'Dwarvish Steelclad': (2, 88, ('Dwarvish Lord',)),
    'Dwarvish Lord': (3, 150, ()),
    'Drake Fighter': (1, 41, ('Drake Warrior',)),
    'Drake Warrior': (2, 81, ('Drake Blademaster',)),
    'Drake Blademaster': (3, 150, ()),
    'Skeleton': (1, 39, ('Revenant', 'Deathblade')),
    'Revenant': (2, 78, ('Draug',)),
    'Deathblade': (2, 100, ()),
    'Draug': (3, 150, ()),
}
STARTERS = {
    'spearman': {'unit_type': 'Spearman', 'faction': 'Loyalists'},
    'elvish-fighter': {'unit_type': 'Elvish Fighter', 'faction': 'Rebels'},
    'orcish-grunt': {'unit_type': 'Orcish Grunt', 'faction': 'Northerners'},
    'dwarvish-fighter': {'unit_type': 'Dwarvish Fighter', 'faction': 'Knalgan Alliance'},
    'drake-fighter': {'unit_type': 'Drake Fighter', 'faction': 'Drakes'},
    'skeleton': {'unit_type': 'Skeleton', 'faction': 'Undead'},
}
MAPS = {
    'isars-cross': {'name': "Isar's Cross", 'scenario_id': 'multiplayer_Isars_Cross',
                    'size': 2, 'sides': ((1, 4), (2, 3))},
    'hexcake': {'name': 'Hexcake', 'scenario_id': 'multiplayer_Hexcake',
                'size': 3, 'sides': ((1, 4, 5), (2, 3, 6))},
    'mokena-prairie': {'name': 'Mokena Prairie', 'scenario_id': 'multiplayer_8p_Mokena_Prairie',
                       'size': 4, 'sides': ((1, 3, 5, 8), (2, 4, 6, 7))},
}
# These identifiers reserve the progression order. Playable mission content is a
# separate delivery; the persistence service must not advertise it as installed.
MISSIONS = ('alliance_training_1', 'alliance_training_2', 'alliance_training_3')
CAMPAIGN_CONTENT_READY = False
LEADER_REWARDS = {'win': 20, 'loss': 10, 'draw': 10}
TEAM_REWARDS = {'win': 100, 'loss': 25, 'draw': 50}


def new_leader(starter_id: str) -> dict:
    starter = STARTERS[starter_id]
    return {'starter_id': starter_id, 'unit_type': starter['unit_type'], 'level': 1,
            'experience': 0, 'total_experience': 0, 'advancement_choices': []}


def award_experience(leader: dict, amount: int) -> dict:
    """Return a new leader; choices are applied only between progression runs."""
    if type(amount) is not int or amount < 0:
        raise ValueError('Experience must be a nonnegative integer.')
    result = deepcopy(leader)
    _, threshold, advances = UNIT_TYPES[result['unit_type']]
    result['total_experience'] += amount
    result['experience'] = result['experience'] + amount if advances else 0
    result['advancement_choices'] = list(advances) if advances and result['experience'] >= threshold else []
    return result


def advance_leader(leader: dict, unit_type: str) -> dict:
    result = deepcopy(leader)
    _, threshold, allowed = UNIT_TYPES[result['unit_type']]
    if unit_type not in allowed or result['experience'] < threshold:
        raise ValueError('This advancement is not available.')
    result['unit_type'] = unit_type
    result['level'] = UNIT_TYPES[unit_type][0]
    result['experience'] -= threshold
    return award_experience(result, 0)


def team_level(experience: int) -> int:
    return 1 + experience // 500


def rating_delta(first_rating: int, second_rating: int, first_score: float) -> int:
    """Symmetric K=24 Elo; clamp exponent and round halves away from zero."""
    expected = 1 / (1 + 10 ** max(-16, min(16, (second_rating - first_rating) / 400)))
    value = 24 * (first_score - expected)
    return math.floor(value + 0.5) if value >= 0 else math.ceil(value - 0.5)
