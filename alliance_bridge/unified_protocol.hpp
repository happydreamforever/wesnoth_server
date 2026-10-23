// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <boost/json.hpp>
#include <algorithm>
#include <initializer_list>
#include <set>
#include <stdexcept>
#include <string>
namespace alliance::unified_protocol {
namespace json=boost::json;
[[noreturn]] inline void invalid(){throw std::runtime_error("Invalid unified product message.");}
inline void keys(const json::object& o,std::initializer_list<const char*> f){if(o.size()!=f.size())invalid();for(auto k:f)if(!o.contains(k))invalid();}
inline std::string text(const json::object& o,const char* k,std::size_t max,bool empty=false){auto v=o.if_contains(k);if(!v||!v->is_string()||v->as_string().size()>max||(!empty&&v->as_string().empty()))invalid();std::string s(v->as_string());if(std::any_of(s.begin(),s.end(),[](unsigned char c){return c<32||c==127;}))invalid();return s;}
inline std::int64_t integer(const json::object&o,const char*k,std::int64_t min=0,std::int64_t max=9223372036854775807LL){auto v=o.if_contains(k);if(!v||!v->is_int64()||v->as_int64()<min||v->as_int64()>max)invalid();return v->as_int64();}
inline const json::array& array(const json::object&o,const char*k,std::size_t max){auto v=o.if_contains(k);if(!v||!v->is_array()||v->as_array().size()>max)invalid();return v->as_array();}
inline const json::object& object(const json::value&v){if(!v.is_object())invalid();return v.as_object();}
inline void selection(const json::value& v){const auto&o=object(v);keys(o,{"hero_id","form_id","hero_level","hero_revision","unit_type","unit_level"});text(o,"hero_id",80);text(o,"form_id",100);text(o,"unit_type",128);integer(o,"hero_level",1);integer(o,"hero_revision");integer(o,"unit_level",0,20);}
inline void heroes(const json::array& list){std::set<std::string> ids;for(const auto&v:list){const auto&o=object(v);keys(o,{"hero_id","name","hero_level","experience","total_experience","revision","forms"});if(!ids.insert(text(o,"hero_id",80)).second)invalid();text(o,"name",128);integer(o,"hero_level",1);integer(o,"experience");integer(o,"total_experience");integer(o,"revision");std::set<std::string>forms;for(const auto&f:array(o,"forms",128)){if(!f.is_string()||f.as_string().empty()||f.as_string().size()>100||!forms.insert(std::string(f.as_string())).second)invalid();}}}
inline void profile(const json::object&o){keys(o,{"id","username","database_generation","heroes"});text(o,"id",36);text(o,"username",24);text(o,"database_generation",36);heroes(array(o,"heroes",256));}
inline bool operation(const std::string& op){return op=="hero_catalog"||op=="story_begin"||op=="story_status"||op=="story_checkpoint"||op=="battle_select_hero"||op=="casual_ticket"||op=="casual_select";}
inline void request(const std::string&op,const json::object&o){
 if(op=="hero_catalog"||op=="casual_ticket")keys(o,{});
 else if(op=="story_begin"){keys(o,{"campaign_id","catalog_version","catalog_sha256"});text(o,"campaign_id",100);text(o,"catalog_version",80);text(o,"catalog_sha256",64);}
 else if(op=="story_status"){keys(o,{"run_id"});text(o,"run_id",36);}
 else if(op=="battle_select_hero"){keys(o,{"battle_id","hero_id","form_id"});text(o,"battle_id",36);text(o,"hero_id",80);text(o,"form_id",100);}
 else if(op=="casual_select"){keys(o,{"game_id","side","hero_id","form_id"});text(o,"game_id",80);integer(o,"side",1,99);text(o,"hero_id",80);text(o,"form_id",100);}
 else if(op=="story_checkpoint"){
  keys(o,{"run_id","checkpoint_id","sequence","scenario_id","next_scenario_id","outcome","heroes","replay_sha256","nonce"});text(o,"run_id",36);text(o,"checkpoint_id",36);integer(o,"sequence",0,2147483647);text(o,"scenario_id",160);text(o,"next_scenario_id",160,true);const auto outcome=text(o,"outcome",8);if(outcome!="win"&&outcome!="loss")invalid();text(o,"replay_sha256",64);text(o,"nonce",64);
  for(const auto&v:array(o,"heroes",128)){const auto&r=object(v);keys(r,{"hero_id","unit_id","form_id","unlocked_forms","earned_experience"});text(r,"hero_id",80);text(r,"unit_id",128);text(r,"form_id",100);integer(r,"earned_experience",0,1000000);for(const auto&f:array(r,"unlocked_forms",128))if(!f.is_string()||f.as_string().empty()||f.as_string().size()>100)invalid();}
 }else invalid();
}
inline void response(const std::string&op,const json::object&o){
 if(op=="casual_ticket"){keys(o,{"ticket","username","account_id","database_generation","expires_at"});text(o,"ticket",43);text(o,"username",24);text(o,"account_id",36);text(o,"database_generation",36);text(o,"expires_at",40);}
 else if(op=="casual_select"){keys(o,{"selection_ticket","selection"});text(o,"selection_ticket",43);selection(o.at("selection"));}
 else if(op=="story_begin"||op=="story_status"){keys(o,{"run_id","account_id","database_generation","campaign_id","catalog_version","catalog_sha256","next_checkpoint","nonce"});text(o,"run_id",36);text(o,"account_id",36);text(o,"database_generation",36);text(o,"campaign_id",100);text(o,"catalog_version",80);text(o,"catalog_sha256",64);integer(o,"next_checkpoint",0,2147483647);text(o,"nonce",64);}
 else if(op=="story_checkpoint"){keys(o,{"run_id","checkpoint_id","next_checkpoint","outcome","rewards","heroes"});text(o,"run_id",36);text(o,"checkpoint_id",36);integer(o,"next_checkpoint",0,2147483647);text(o,"outcome",8);heroes(array(o,"heroes",256));for(const auto&v:array(o,"rewards",128)){const auto&r=object(v);keys(r,{"hero_id","experience_awarded"});text(r,"hero_id",80);integer(r,"experience_awarded",0,1000020);}}
 else if(op=="hero_catalog"){keys(o,{"catalog_version","catalog_sha256","heroes","forms","campaigns"});text(o,"catalog_version",80);text(o,"catalog_sha256",64);array(o,"heroes",256);array(o,"forms",1024);array(o,"campaigns",64);}
 else if(op!="battle_select_hero")invalid();
}
}
