// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "world_protocol.hpp"

namespace alliance::court_protocol {
namespace json = boost::json;
using namespace unified_protocol;
inline bool operation(const std::string& op) { return op == "court_query" || op == "court_command"; }
inline void request(const std::string& outer, const json::object& body) {
    if(!operation(outer)) invalid();
    const bool command = outer == "court_command";
    keys(body, command ? std::initializer_list<const char*>{"version", "operation", "payload"}
                       : std::initializer_list<const char*>{"version", "query", "payload"});
    integer(body, "version", 1, 1);
    const auto name = text(body, command ? "operation" : "query", 64);
    static const std::set<std::string> queries = {"snapshot", "areas", "area", "castle",
        "my_team", "teams", "team", "plans", "plan", "competitions", "competition", "shop",
        "wallet", "notifications", "history", "command_status", "room_quote"};
    static const std::set<std::string> commands = {"create_team", "apply_team", "withdraw_application",
        "approve_member", "reject_member", "leave_team", "remove_member", "rename_team", "transfer_captain", "set_allowance", "relocate",
        "request_cash", "donate", "buy_hero", "buy_item", "buy_trial", "read_notification", "room_consent",
        "request_attack_approval", "approve_attack", "attack", "defend", "cancel_attack", "defense_consent",
        "set_defense", "withdraw_defense", "create_plan", "approve_plan", "cancel_plan", "join_match",
        "leave_match", "select_hero", "select_item", "ready", "enter_competition", "leave_competition"};
    if(!(command ? commands : queries).count(name)) invalid();
    const auto& payload = object(body.at("payload"));
    world_protocol::bounded(payload);
    if(command) flexible_protocol::id(payload, "command_id");
    if(json::serialize(body).size() > 65536) invalid();
}
inline void response(const json::object& body) {
    keys(body, {"version", "database_generation", "actor_id", "server_time", "data"});
    integer(body, "version", 1, 1);
    flexible_protocol::id(body, "database_generation");
    flexible_protocol::id(body, "actor_id");
    text(body, "server_time", 64);
    object(body.at("data"));
    world_protocol::bounded(body.at("data"));
    if(json::serialize(body).size() > 250000) invalid();
}
inline std::string public_error(const std::string& code) {
    static const std::map<std::string,std::string> errors = {
        {"admission_required", "Review and approve the Room fee first."},
        {"already_joined", "You already have a seat here."},
        {"balance_changed", "Your balance changed. Refresh and review the cost."},
        {"balance_limit", "This wallet has reached its balance limit."},
        {"capacity", "The available places are full."},
        {"captain_transfer_required", "Choose another captain before leaving."},
        {"castle_capacity", "Your Team has no free Castle holding slot."},
        {"castle_committed", "Finish this Castle contest first."},
        {"cooldown", "Wait briefly before another Castle challenge."},
        {"daily_limit", "No trials remain today."},
        {"extra_trial_limit", "Today’s extra-trial purchase limit has been reached."},
        {"generation_changed", "This game has restarted. Sign in again."},
        {"hero_already_owned", "You already own this hero. No Crowns were charged."},
        {"hero_required", "Choose an owned hero first."},
        {"hold_finalized", "This payment was already finalized. Refresh its receipt."},
        {"hold_unavailable", "This payment is unavailable. Refresh its receipt."},
        {"invalid_castle", "Choose an available Castle."},
        {"invalid_evidence", "This battle result could not be verified."},
        {"invalid_hold", "Review this payment again."},
        {"invalid_map", "Choose a supported battle map."},
        {"invalid_opponent", "Choose an opposing Team in your home Area."},
        {"invalid_ticket", "This admission expired. Review it again."},
        {"inventory_limit", "Your item inventory is full."},
        {"item_finalized", "This item use was already resolved."},
        {"item_limit", "Only one item may be selected for a battle."},
        {"item_unavailable", "This item is unavailable or already reserved."},
        {"location_busy", "This location still has Teams, ownership or events."},
        {"not_joined", "Join a battle seat first."},
        {"not_member", "Choose a current Team member."},
        {"pending_limit", "Wait for your pending requests to be reviewed."},
        {"progression_limit", "This collection has reached its progression limit."},
        {"protected", "This Castle is protected. Wait for the countdown."},
        {"replay_unavailable", "This replay is not available."},
        {"request_changed", "This request changed. Refresh and review it."},
        {"request_decided", "This request was already reviewed."},
        {"reservation_lost", "The battle reservation expired. Refresh its status."},
        {"result_conflict", "The saved battle result differs. Ask the host to review it."},
        {"room_conflict", "This Room admission is already in use."},
        {"room_unavailable", "This Room is no longer available."},
        {"same_area", "This is already your Team’s home Area."},
        {"snapshot_conflict", "The saved selection changed. Review it again."},
        {"stale_proposal", "This proposal changed. Review the current version."},
        {"transaction_conflict", "Another action changed this record. Refresh and try again."},
        {"trial_finalized", "This trial was already finalized."},
        {"trial_unavailable", "This trial is no longer available."},
        {"unsupported_command", "This action is unavailable in this game version."},
        {"unsupported_query", "This page is unavailable in this game version."},
        {"wallet_unavailable", "This wallet is unavailable."},
        {"wrong_castle", "Choose the correct type of Castle."},
        {"invalid_input", "Review the selected settings."},
        {"forbidden", "This action is not available to your account."},
        {"not_found", "This record is no longer available."},
        {"account_unavailable", "Please sign in to an active player account."},
        {"unsupported_ruleset", "Update the game and server before continuing."},
        {"unsupported_protocol", "Update the game and server before continuing."},
        {"conflict", "The selection changed. Refresh and review it."},
        {"command_conflict", "Check the original action before trying again."},
        {"stale_revision", "Updated—review changes before confirming."},
        {"price_changed", "Prices changed—review the current cost."},
        {"insufficient_funds", "There are not enough available Crowns."},
        {"team_required", "Join a Team first."},
        {"already_member", "You already belong to a Team."},
        {"team_full", "This Team is full."},
        {"area_full", "This Area has no place for another Team."},
        {"area_unavailable", "This Area is not currently open."},
        {"castle_unavailable", "This Castle is not currently open."},
        {"castle_busy", "Another battle reserves this Castle."},
        {"castle_protected", "This Castle is protected. Wait for the countdown."},
        {"hero_locked", "Choose an owned hero and available form."},
        {"team_committed", "Finish this Team’s commitments first."},
        {"player_committed", "Leave or finish your current battle commitment first."},
        {"quota_exhausted", "Today’s trial limit has been reached."},
        {"allowance_exceeded", "Ask the captain to approve this Team expense."},
        {"application_pending", "You already have a pending Team application."},
        {"application_expired", "This application has expired."},
        {"application_decided", "This application has already been resolved."},
        {"name_taken", "That Team name is already in use."},
        {"confirmation_required", "Review and confirm this action."},
        {"invalid_state", "This action is no longer available. Refresh the page."},
        {"stale_hero", "Your hero changed. Select it again before Ready."},
        {"battle_locked", "This battle is locked. Refresh its current status."},
        {"battle_full", "This battle has no free player seat."},
        {"already_owned", "This hero is already owned."}};
    const auto found = errors.find(code);
    return found == errors.end() ? std::string{} : found->second;
}
}
