// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <boost/json.hpp>
#include <algorithm>
#include <initializer_list>
#include <map>
#include <stdexcept>
#include <string>

// Mirrored in the server bridge. This small, closed schema prevents either
// endpoint from turning the progression extension into a generic HTTP proxy.
namespace alliance::progression_protocol {
namespace json = boost::json;
[[noreturn]] inline void invalid() { throw std::runtime_error("Invalid progression message."); }
inline bool operation(const std::string& op) {
    return op == "progression_catalog" || op == "progression_start" ||
        op == "progression_status" || op == "progression_finish" ||
        op == "progression_cancel" || op == "progression_advance" || op == "progression_history" ||
        op == "coordination_orders" || op == "coordination_post" || op == "shared_review" || op == "shared_confirm";
}
inline std::string public_error(const std::string& code) {
    static const std::map<std::string,std::string> messages={
        {"invalid_input","Check the selected action and entered text."},
        {"not_found","The selected mission, team or battle is no longer available. Refresh its list."},
        {"forbidden","This action is not permitted for the current player or captain."},
        {"suspended","This account is suspended. Contact the local administrator."},
        {"busy","This player or team is reserved by an unfinished game. Review that game first."},
        {"mission_locked","Complete the previous campaign mission first."},
        {"invalid_mission","This mission version is not supported by the server."},
        {"advancement_required","Choose an available leader advancement in Campaign progression before preparing or starting another game."},
        {"invalid_advancement","That advancement is not available. Refresh your personal leader."},
        {"invalid_result","The saved result could not be verified. Preserve its replay and report this message."},
        {"result_conflict","The result is incomplete, disputed or changed. Review it before confirming."},
        {"invalid_state","This action is unavailable in the game's current state. Refresh its details."},
        {"reservation_conflict","Another game reserved this player or team. Refresh the plan."},
        {"room_conflict","Another shared room already owns this plan. Reconnect to the current room."},
        {"room_expired","The waiting room expired. Refresh the draft and join again."},
        {"not_member","You are no longer a member of this team."},
        {"result_agreement_required","All player results and both captain confirmations are required."},
        {"snapshot_conflict","The saved team or leader changed. Refresh the battle plan."},
        {"stale_account","The account changed. Refresh before confirming this action."},
        {"conflict","The requested change conflicts with current saved state. Refresh before trying again."},
        {"rate_limited","Too many requests. Wait briefly before trying again."}
    };
    const auto found=messages.find(code);return found==messages.end()?std::string{}:found->second;
}
inline void keys(const json::object& obj, std::initializer_list<const char*> fields) {
    if(obj.size() != fields.size()) invalid();
    for(const auto* field : fields) if(!obj.contains(field)) invalid();
}
inline std::string text(const json::object& obj, const char* key, std::size_t max, bool empty=false) {
    const auto* v=obj.if_contains(key);
    if(!v || !v->is_string() || v->as_string().size()>max || (!empty && v->as_string().empty())) invalid();
    const std::string s(v->as_string());
    if(std::any_of(s.begin(),s.end(),[](unsigned char c){return c<32 || c==127;})) invalid();
    return s;
}
inline bool hex(const std::string& s, std::size_t length) {
    return s.size()==length && std::all_of(s.begin(),s.end(),[](char c){return (c>='0'&&c<='9')||(c>='a'&&c<='f');});
}
inline bool uuid(const std::string& s) {
    if(s.size()!=36) return false;
    std::string digits;
    for(std::size_t i=0;i<s.size();++i) {
        if(i==8||i==13||i==18||i==23) { if(s[i]!='-') return false; }
        else digits+=s[i];
    }
    return hex(digits,32);
}
inline bool mission(const std::string& id) {
    return id=="alliance_training_1"||id=="alliance_training_2"||id=="alliance_training_3";
}
inline std::string order_text(const json::object& obj) {
    const auto* v=obj.if_contains("text");
    if(!v||!v->is_string()||v->as_string().size()<3||v->as_string().size()>500) invalid();
    const std::string value(v->as_string());
    if(std::any_of(value.begin(),value.end(),[](unsigned char c){return (c<32&&c!='\n'&&c!='\t')||c==127;})) invalid();
    return value;
}
inline std::string target(const std::string& op) {
    if(op.rfind("progression_",0)==0) return "/internal/v1/progression/"+op.substr(12);
    if(op.rfind("coordination_",0)==0) return "/internal/v1/coordination/"+op.substr(13);
    if(op=="shared_review"||op=="shared_confirm") return "/internal/v1/shared/"+op.substr(7);
    invalid();
}
inline void request(const std::string& op, const json::object& body) {
    if(!operation(op)) invalid();
    if(op=="coordination_orders"||op=="coordination_post") {
        if(op=="coordination_orders") keys(body,{"team_id"});
        else {keys(body,{"team_id","text"});order_text(body);}
        if(!uuid(text(body,"team_id",36))) invalid();
    } else if(op=="shared_review"||op=="shared_confirm") {
        if(op=="shared_review") keys(body,{"run_id"});
        else {keys(body,{"run_id","candidate_digest"});if(!hex(text(body,"candidate_digest",64),64)) invalid();}
        if(!uuid(text(body,"run_id",36))) invalid();
    } else if(op=="progression_catalog"||op=="progression_history") keys(body,{});
    else if(op=="progression_start") {
        keys(body,{"mission_id"}); if(!mission(text(body,"mission_id",32))) invalid();
    } else if(op=="progression_status"||op=="progression_cancel") {
        keys(body,{"run_id"}); if(!uuid(text(body,"run_id",36))) invalid();
    } else if(op=="progression_advance") {
        keys(body,{"unit_type"}); const auto unit=text(body,"unit_type",64);
        if(!std::all_of(unit.begin(),unit.end(),[](char c){return (c>='a'&&c<='z')||(c>='A'&&c<='Z')||c==' ';})) invalid();
    } else {
        keys(body,{"run_id","mission_id","mission_version","nonce","outcome","replay_sha256","format"});
        if(!uuid(text(body,"run_id",36))||!mission(text(body,"mission_id",32))||
           text(body,"mission_version",64)!="progression-campaign-v1"||
           !hex(text(body,"nonce",64),64)||!hex(text(body,"replay_sha256",64),64)||
           text(body,"format",64)!="alliance-native-campaign-result-v1") invalid();
        const auto result=text(body,"outcome",8); if(result!="win"&&result!="loss") invalid();
    }
}
inline int number(const json::object& body, const char* key, int minimum=0, int maximum=2147483647) {
    const auto* v=body.if_contains(key);
    if(!v||!v->is_int64()||v->as_int64()<minimum||v->as_int64()>maximum) invalid();
    return static_cast<int>(v->as_int64());
}
inline void boolean(const json::object& body, const char* key) {
    if(!body.contains(key)||!body.at(key).is_bool()) invalid();
}
inline const json::object& object(const json::object& body, const char* key) {
    if(!body.contains(key)||!body.at(key).is_object()) invalid();
    return body.at(key).as_object();
}
inline const json::array& array(const json::object& body, const char* key, std::size_t maximum) {
    if(!body.contains(key)||!body.at(key).is_array()||body.at(key).as_array().size()>maximum) invalid();
    return body.at(key).as_array();
}
inline void profile(const json::object& value) {
    keys(value,{"id","username","starter_id","unit_type","level","experience","total_experience","advancement_choices"});
    if(!uuid(text(value,"id",36))) invalid();
    text(value,"username",24);text(value,"starter_id",40);text(value,"unit_type",64);
    number(value,"level",1,3);number(value,"experience");number(value,"total_experience");
    for(const auto& choice:array(value,"advancement_choices",3))
        if(!choice.is_string()||choice.as_string().empty()||choice.as_string().size()>64) invalid();
}
inline void run(const json::object& value, bool history=false) {
    keys(value,{"id","account_id","username","mission_id","mission_name","mission_version","ruleset_version", "state", "unit_type","leader_level","nonce","created_at","finished_at","outcome","experience_awarded"});
    if(!uuid(text(value,"id",36))||!uuid(text(value,"account_id",36))||!mission(text(value,"mission_id",32))||
       text(value,"mission_version",64)!="progression-campaign-v1"||text(value,"ruleset_version",32)!="alliance-v1") invalid();
    text(value,"username",24);text(value,"mission_name",100);text(value,"unit_type",64);
    number(value,"leader_level",1,3);number(value,"experience_awarded",0,20);
    const auto state=text(value,"state",16);
    if(state!="running"&&state!="completed"&&state!="cancelled") invalid();
    const auto nonce=text(value,"nonce",64,true);
    if(history||state!="running") {if(!nonce.empty()) invalid();}
    else if(!nonce.empty()&&!hex(nonce,64)) invalid();
    text(value,"created_at",40);text(value,"finished_at",40,true);
    const auto outcome=text(value,"outcome",8,true);
    if(outcome!=""&&outcome!="win"&&outcome!="loss") invalid();
    if(state=="completed"&&outcome.empty()) invalid();
}
inline void order(const json::object& value) {
    keys(value,{"id","author_id","author_name","text","created_at"});
    if(!uuid(text(value,"id",36))||!uuid(text(value,"author_id",36))) invalid();
    text(value,"author_name",24);text(value,"created_at",40);order_text(value);
}
inline void review(const json::object& body) {
    keys(body,{"run_id","state","review_state","candidate_digest","winner_team_id","draw","reports_received","required_reports","captains_approved","revision"});
    if(!uuid(text(body,"run_id",36))) invalid();
    const auto state=text(body,"state",16);
    if(state!="draft"&&state!="running"&&state!="completed"&&state!="cancelled") invalid();
    const auto status=text(body,"review_state",32);
    if(status!="waiting_for_players"&&status!="disputed"&&status!="awaiting_captains"&&status!="agreed"&&status!="settled"&&status!="cancelled") invalid();
    const auto digest=text(body,"candidate_digest",64,true);if(!digest.empty()&&!hex(digest,64)) invalid();
    const auto winner=text(body,"winner_team_id",36,true);if(!winner.empty()&&!uuid(winner)) invalid();
    boolean(body,"draw");number(body,"reports_received",0,8);number(body,"required_reports",4,8);
    number(body,"revision");
    number(body,"captains_approved",0,2);
}
inline void response(const std::string& op,const json::object& body) {
    if(op=="coordination_orders") {
        keys(body,{"team_id","team_name","has_more","orders"});
        if(!uuid(text(body,"team_id",36))) invalid();
        text(body,"team_name",40);boolean(body,"has_more");
        for(const auto& row:array(body,"orders",10)) {if(!row.is_object()) invalid();order(row.as_object());}
        return;
    }
    if(op=="coordination_post") {keys(body,{"order"});order(object(body,"order"));return;}
    if(op=="shared_review"||op=="shared_confirm") {review(body);return;}
    if(op=="progression_catalog") {
        keys(body,{"profile","missions","active_run"});profile(object(body,"profile"));
        const auto& missions=array(body,"missions",3);if(missions.size()!=3) invalid();
        for(std::size_t i=0;i<missions.size();++i) {
            if(!missions[i].is_object()) invalid();
            const auto& m=missions[i].as_object();
            keys(m,{"id","name","version","unlocked","completed","victory_experience"});
            if(text(m,"id",32)!="alliance_training_"+std::to_string(i+1)||text(m,"version",64)!="progression-campaign-v1") invalid();
            text(m,"name",100);boolean(m,"unlocked");boolean(m,"completed");number(m,"victory_experience",20,20);
        }
        if(!body.at("active_run").is_null()) run(object(body,"active_run"));
    } else if(op=="progression_advance") {keys(body,{"profile"});profile(object(body,"profile"));}
    else if(op=="progression_history") {
        keys(body,{"runs","has_more"});boolean(body,"has_more");
        for(const auto& r:array(body,"runs",20)) {if(!r.is_object()) invalid();run(r.as_object(),true);}
    } else if(op=="progression_finish") {
        keys(body,{"run","profile","experience_awarded"});run(object(body,"run"));profile(object(body,"profile"));
        number(body,"experience_awarded",0,20);if(text(object(body,"run"),"state",16)!="completed") invalid();
    } else {
        if(!operation(op)) invalid();
        keys(body,{"run"});run(object(body,"run"));
        if(op=="progression_start"&&(text(object(body,"run"),"state",16)!="running"||!hex(text(object(body,"run"),"nonce",64),64))) invalid();
        if(op=="progression_cancel"&&text(object(body,"run"),"state",16)!="cancelled") invalid();
    }
}
} // namespace alliance::progression_protocol
