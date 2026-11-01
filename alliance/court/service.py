"""Explicit replacement service; importing it never initializes or migrates data.

Only the command allowlists below may be dispatched from a player connection.
Worker authority is a separate, service-authenticated native boundary.
"""
from ..domain import LegacyAllianceService
from ..product import UnifiedProduct
from ..admin_management import AdminManagement
from .base import CourtBase, exact, fail
from .geography import GeographyMixin
from .teams import TeamMixin
from .wallets import EconomyMixin
from .battles import BattleMixin
from .queries import QueryMixin
from .rooms import RoomMixin


PLAYER_COMMANDS = frozenset('''create_team apply_team withdraw_application
approve_member reject_member leave_team remove_member rename_team transfer_captain set_allowance relocate
request_cash donate buy_hero buy_item buy_trial read_notification room_consent
request_attack_approval approve_attack attack defend cancel_attack
defense_consent set_defense withdraw_defense create_plan approve_plan cancel_plan
join_match leave_match select_hero select_item ready enter_competition leave_competition'''.split())
ADMIN_COMMANDS = frozenset('''approve_cash reject_cash set_activation set_rules
admin_create_competition admin_lock_competition admin_start_round
admin_cancel_competition admin_cancel_match'''.split())


class CourtService(QueryMixin, RoomMixin, BattleMixin, EconomyMixin, TeamMixin,
                   GeographyMixin, CourtBase, AdminManagement, UnifiedProduct,
                   LegacyAllianceService):
    def court_command(self, actor, request):
        exact(request, ('version', 'operation', 'payload'))
        if set(request) != {'version', 'operation', 'payload'} or type(request['version']) is not int or request['version'] != 1:
            fail('unsupported_protocol', 'Update the game to use Court.')
        operation = request['operation']
        if not isinstance(operation, str) or operation not in PLAYER_COMMANDS:
            fail('unsupported_command', 'This player action is unavailable.')
        return self._execute(actor, operation, request['payload'], getattr(self, '_court_' + operation))

    def court_admin_command(self, actor, request):
        exact(request, ('version', 'operation', 'payload'))
        if set(request) != {'version', 'operation', 'payload'} or type(request['version']) is not int or request['version'] != 1:
            fail('unsupported_protocol', 'Refresh the administration page.')
        operation = request['operation']
        if not isinstance(operation, str) or operation not in ADMIN_COMMANDS:
            fail('unsupported_command', 'This administration action is unavailable.')
        return self._execute(actor, operation, request['payload'], getattr(self, '_court_' + operation), admin=True)
