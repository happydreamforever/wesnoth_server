// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "flexible_protocol.hpp"
#include <map>
#include <vector>

namespace alliance::world_protocol {
namespace json = boost::json;
using namespace alliance::unified_protocol;
inline bool operation(const std::string& op) { return op == "world_query" || op == "world_command"; }
inline void bounded(const json::value& value, unsigned depth=0) {
    if(depth > 10) invalid();
    if(value.is_object()) {
        if(value.as_object().size()>64) invalid();
        for(const auto& item:value.as_object()) {
            const std::string key(item.key());
            if(key.empty() || key.size()>100 || key.find('$')!=std::string::npos || key.find('.')!=std::string::npos) invalid();
            for(unsigned char c:key) if(c<32 || c==127) invalid();
            for(const char* secret:{"password", "password_hash", "bridge_secret", "private_key", "worker_ticket", "worker_secret", "native_evidence"}) if(key==secret) invalid();
            bounded(item.value(),depth+1);
        }
    } else if(value.is_array()) {
        if(value.as_array().size()>256) invalid();
        for(const auto& item:value.as_array()) bounded(item,depth+1);
    } else if(value.is_string()) {
        if(value.as_string().size()>4096) invalid();
        for(unsigned char c:value.as_string()) if(c<32 || c==127) invalid();
    } else if(value.is_double() || value.is_uint64()) invalid();
}
inline void request(const std::string& outer, const json::object& body) {
    keys(body,{"operation","payload"});
    const auto op=text(body,"operation",32);
    const auto& p=object(body.at("payload"));
    static const std::map<std::string,std::vector<std::string>> queries={
        {"snapshot",{}},{"company",{}},{"catalog",{}},{"castle",{"castle_id"}},
        {"battles",{}},{"history",{}},{"battle",{"run_id"}},{"command_status",{"command_id"}}};
    static const std::map<std::string,std::vector<std::string>> commands={
        {"company_initialize",{}},{"company_recruit",{"expected_revision","unit_type"}},
        {"company_retire",{"expected_revision","soldier_id"}},
        {"company_select",{"expected_revision","hero_id","form_id","soldier_ids","bracket"}},
        {"company_preferences",{"expected_revision","soldier_id","preferences"}},
        {"company_rest",{"expected_revision"}},{"company_expedition",{"expected_revision","mission_id"}},
        {"skirmish_create",{"plan_id"}},{"battle_confirm",{"run_id"}},{"enroll",{}},{"station",{"castle_id"}},{"roadworks",{"castle_id"}},{"roadworks_propose",{"castle_id"}},
        {"governor",{"castle_id","account_id"}},{"defense_offer",{"castle_id","bracket"}},
        {"defense_approve",{"assignment_id"}},{"defense_withdraw",{"assignment_id"}},
        {"attack",{"origin_id","target_id","bracket"}},{"battle_join",{"run_id","team_id"}},
        {"battle_ready",{"run_id","ready"}},{"battle_approve",{"run_id"}},{"battle_cancel",{"run_id"}},
        {"war_propose",{"opponent_team_id","target_ids","objective_area_id"}},{"war_approve",{"war_id"}},{"war_cancel",{"war_id"}}};
    if(!operation(outer)) invalid();
    const auto& table=outer=="world_query"?queries:commands;
    auto found=table.find(op); if(found==table.end()) invalid();
    std::set<std::string> allowed(found->second.begin(),found->second.end());
    for(const auto& key:allowed) if(!p.contains(key)) invalid();
    if(outer=="world_command") { allowed.insert("command_id"); flexible_protocol::id(p,"command_id"); }
    if(op=="history") { allowed.insert("before"); allowed.insert("limit"); }
    if(op=="attack") allowed.insert("war_id");
    for(const auto& item:p) if(!allowed.count(std::string(item.key()))) invalid();
    bounded(p);
    if(p.contains("expected_revision")) integer(p,"expected_revision",0,2147483647);
    if(p.contains("limit")) integer(p,"limit",1,30);
    if(p.contains("before")) flexible_protocol::id(p,"before",true);
    for(const char* key:{"command_id","plan_id","soldier_id","castle_id","account_id","assignment_id","target_id","run_id","team_id","opponent_team_id","war_id"})
        if(p.contains(key) && !(op=="governor" && std::string(key)=="account_id" && p.at(key).is_null())) flexible_protocol::id(p,key);
    if(p.contains("origin_id")) {const auto origin=text(p,"origin_id",41);if(!flexible_protocol::uuid(origin) && !(origin.substr(0,5)=="camp:" && flexible_protocol::uuid(origin.substr(5)))) invalid();}
    if(p.contains("objective_area_id") && !p.at("objective_area_id").is_null()) flexible_protocol::id(p,"objective_area_id");
    if(p.contains("ready")) flexible_protocol::boolean(p,"ready");
    if(p.contains("bracket")) {const auto b=text(p,"bracket",16);if(b!="scout"&&b!="veteran"&&b!="champion") invalid();}
    for(const char* key:{"hero_id","form_id","unit_type","mission_id"}) if(p.contains(key)) text(p,key,128);
    for(const char* key:{"soldier_ids","target_ids"}) if(p.contains(key)) {
        const auto& a=array(p,key,std::string(key)=="soldier_ids"?4:6);
        if(std::string(key)=="target_ids"&&a.empty()) invalid();
        std::set<std::string> ids;
        for(const auto& v:a) {if(!v.is_string()) invalid();std::string id(v.as_string());if(!flexible_protocol::uuid(id)||!ids.insert(id).second) invalid();}
    }
    if(p.contains("preferences")) {
        const auto& prefs=object(p.at("preferences"));if(prefs.size()>32) invalid();
        for(const auto& item:prefs) if(item.key().empty()||item.key().size()>128||!item.value().is_string()||item.value().as_string().empty()||item.value().as_string().size()>128) invalid();
    }
    if(json::serialize(body).size()>65536) invalid();
}
inline void response(const json::object& body) {
    keys(body,{"version","balance_revision","database_generation","actor_id","data"});
    integer(body,"version",1,1);
    if(text(body,"balance_revision",64)!="world-company-1") invalid();
    flexible_protocol::id(body,"database_generation");flexible_protocol::id(body,"actor_id");
    object(body.at("data"));bounded(body.at("data"));
    if(json::serialize(body).size()>250000) invalid();
}
inline std::string public_error(const std::string& code) {
    static const std::map<std::string,std::string> messages={
        {"invalid_input","Review the selected company and battle settings."},
        {"forbidden","This action is not available to your account."},
        {"not_found","This company or battle is no longer available."},
        {"conflict","The plan changed. Refresh and review it before continuing."},
        {"stale_revision","The company changed. Review the updated selection."},
        {"command_conflict","This action could not be confirmed. Refresh its current status."},
        {"hero_required","Complete a story scenario to earn your first hero."},
        {"team_required","Join a team to take part in territorial battles."},
        {"world_unavailable","The host has not opened the world yet."},
        {"not_enrolled","Enter the world with your current team first."},
        {"force_review","This company needs a force review before deployment."},
        {"round_locked","This round is locked. Wait for the next planning phase."},
        {"round_limit","This company or team already has an order for this round."},
        {"wrong_station","Your company is not stationed at that origin."},
        {"no_route","There is no eligible route to that castle."},
        {"castle_busy","Another committed engagement reserves this castle."},
        {"war_required","Both captains must approve the territorial objective first."},
        {"busy","This company is committed elsewhere."},
        {"wounded","These units need recovery before deployment."},
        {"capacity","There is no space for another soldier or company here."},
        {"invalid_state","This action is no longer available. Refresh and review the current state."},
        {"insufficient_supply","Your team needs more Supply for this improvement."},
        {"already_built","This castle already has Roadworks."},
        {"already_enrolled","This team is already enrolled."},
        {"already_initialized","This world has already been initialized."},
        {"already_joined","Your company already participates in this battle."},
        {"battle_locked","This battle is locked. Refresh its current status."},
        {"consent_required","The selected owners or captains still need to approve."},
        {"different_area","Choose teams from the same administrative area for this skirmish."},
        {"invalid_lineup","Review the participating companies and side assignments."},
        {"invalid_mission","Choose one of the available Company expeditions."},
        {"membership_changed","Team membership changed. Review this plan."},
        {"mission_locked","This hero is committed to another persistent mission."},
        {"reservation_lost","The battle reservation is unavailable. Refresh before continuing."},
        {"result_conflict","The battle evidence needs host review. No new rewards were applied."},
        {"selected","Remove this soldier from the deployment tray before retiring it."},
        {"unfinished_battles","Resolve the remaining engagements before advancing the round."},
        {"wrong_phase","This action is unavailable in the current world phase."},
        {"unsupported_ruleset","Update the game and server before continuing."}};
    auto i=messages.find(code);return i==messages.end()?std::string{}:i->second;
}
}
