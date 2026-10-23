"""Versioned persistent hero progression, separate from Wesnoth unit tiers."""
from copy import deepcopy
from functools import lru_cache
import hashlib
import json
from pathlib import Path

MAX_XP = 9223372036854775807


def spent_experience(level):
    """XP spent reaching level L; level one starts at zero."""
    return 5 * (level - 1) * level * (2 * level - 1) // 6 + 15 * (level - 1)


def hero_progress(total):
    if type(total) is not int or not 0 <= total <= MAX_XP:
        raise ValueError('Hero experience is outside the storage range.')
    low, high = 1, 2
    while spent_experience(high) <= total:
        high *= 2
    while low + 1 < high:
        middle = (low + high) // 2
        if spent_experience(middle) <= total:
            low = middle
        else:
            high = middle
    return {'hero_level': low, 'experience': total - spent_experience(low),
            'total_experience': total}


def scaled_stat(base, level, percent):
    if type(base) is not int or base < 0 or type(level) is not int or level < 1:
        raise ValueError('Invalid hero stat.')
    # Integer round-half-up; never changes engine unit level or attack count.
    result = (base * (100 + percent * (level - 1)) + 50) // 100
    if result > 2147483647:
        raise ValueError('Hero combat stat exceeds the native engine range.')
    return result


@lru_cache(maxsize=1)
def load_catalog():
    path = Path(__file__).with_name('hero_catalog.json')
    data = path.read_bytes()
    catalog = json.loads(data)
    return catalog, hashlib.sha256(data).hexdigest()


def catalog_hero(hero_id):
    catalog, _ = load_catalog()
    for hero in catalog['heroes']:
        if hero['id'] == hero_id:
            return deepcopy(hero)
    raise ValueError('Unknown hero.')


def catalog_form(hero_id, form_id):
    hero = catalog_hero(hero_id)
    catalog, _ = load_catalog()
    for form in catalog['forms']:
        if form['id'] == form_id and form['hero_id'] == hero_id:
            return hero, form
    raise ValueError('Unknown hero form.')
