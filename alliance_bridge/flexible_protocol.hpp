// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include "unified_protocol.hpp"
namespace alliance::flexible_protocol {
namespace json=boost::json;
using namespace alliance::unified_protocol;
inline bool uuid(const std::string& s){if(s.size()!=36)return false;for(std::size_t i=0;i<s.size();++i){if(i==8||i==13||i==18||i==23){if(s[i]!='-')return false;}else if(!((s[i]>='a'&&s[i]<='f')||(s[i]>='0'&&s[i]<='9')))return false;}return true;}
inline void id(const json::object&o,const char*k,bool empty=false){const auto s=text(o,k,36,empty);if(!(empty&&s.empty())&&!uuid(s))invalid();}
inline void boolean(const json::object&o,const char*k){auto v=o.if_contains(k);if(!v||!v->is_bool())invalid();}
inline void settings(const json::value&v){const auto&o=object(v);keys(o,{"gold","base_income","turns","fog","shroud","observers"});integer(o,"gold",0,1000);integer(o,"base_income",0,20);if(integer(o,"turns",-1,1000)==0)invalid();for(auto k:{"fog","shroud","observers"})boolean(o,k);}
inline int map_size(const std::string& s){if(s=="isars-cross")return 2;if(s=="hexcake")return 3;if(s=="mokena-prairie")return 4;invalid();}
inline bool ai(const std::string& f,const std::string& leader){
 if(f=="Loyalists"){for(const char* allowed:{"Lieutenant","Swordsman","Pikeman","Javelineer","Shock Trooper","Longbowman","White Mage","Red Mage"})if(leader==allowed)return true;return false;}
 if(f=="Rebels"){for(const char* allowed:{"Elvish Captain","Elvish Hero","Elvish Ranger","Elvish Marksman","Elvish Druid","Elvish Sorceress","White Mage","Red Mage","Elder Wose"})if(leader==allowed)return true;return false;}
 if(f=="Northerners"){for(const char* allowed:{"Orcish Warrior","Troll","Troll Rocklobber","Orcish Crossbowman","Orcish Slayer"})if(leader==allowed)return true;return false;}
 if(f=="Knalgan Alliance"){for(const char* allowed:{"Dwarvish Steelclad","Dwarvish Thunderguard","Dwarvish Stalwart","Rogue","Trapper"})if(leader==allowed)return true;return false;}
 if(f=="Undead"){for(const char* allowed:{"Dark Sorcerer","Revenant","Deathblade","Bone Shooter","Necrophage"})if(leader==allowed)return true;return false;}
 if(f=="Drakes"){for(const char* allowed:{"Drake Flare","Fire Drake","Drake Arbiter","Drake Thrasher","Drake Warrior","Saurian Oracle"})if(leader==allowed)return true;return false;}
 if(f=="Dunefolk"){for(const char* allowed:{"Dune Explorer","Dune Swordsman","Dune Spearguard","Dune Scorcher","Dune Apothecary"})if(leader==allowed)return true;return false;}
 return false;
}
inline void slot(const json::object&o){keys(o,{"side","kind","account_id","ai_faction","ai_leader"});integer(o,"side",1,8);const auto kind=text(o,"kind",8),account=text(o,"account_id",36,true),f=text(o,"ai_faction",32,true),l=text(o,"ai_leader",64,true);if(kind!="open"&&kind!="reserved"&&kind!="ai"&&kind!="closed")invalid();if(kind=="reserved"){if(!uuid(account))invalid();}else if(!account.empty())invalid();if(kind=="ai"){if(!ai(f,l))invalid();}else if(!f.empty()||!l.empty())invalid();}
inline void slots(const json::array&a,int count){if(a.size()!=static_cast<std::size_t>(count))invalid();std::set<int>s;std::set<std::string>accounts;for(const auto&v:a){const auto&o=object(v);slot(o);if(!s.insert(integer(o,"side",1,8)).second)invalid();auto account=text(o,"account_id",36,true);if(!account.empty()&&!accounts.insert(account).second)invalid();}}
inline bool operation(const std::string& op){return op=="publish_plan"||op=="edit_plan"||op=="join_plan"||op=="leave_plan"||op=="approve_plan"||op=="ready_plan"||op=="select_plan_hero";}
inline void request(const std::string&op,const json::object&o){
 if(op=="publish_plan"){keys(o,{"team_id","opponent_team_id","map_id","settings","slots"});id(o,"team_id");id(o,"opponent_team_id");}
 else if(op=="edit_plan")keys(o,{"battle_id","revision","map_id","settings","slots"});
 else if(op=="join_plan"){keys(o,{"battle_id","revision","side"});integer(o,"side",1,8);}
 else if(op=="leave_plan"||op=="approve_plan")keys(o,{"battle_id","revision"});
 else if(op=="ready_plan"){keys(o,{"battle_id","revision","ready"});boolean(o,"ready");}
 else if(op=="select_plan_hero"){keys(o,{"battle_id","revision","hero_id","form_id"});text(o,"hero_id",80);text(o,"form_id",100);}
 else invalid();
 if(op!="publish_plan"){id(o,"battle_id");integer(o,"revision",1);}
 if(op=="publish_plan"||op=="edit_plan"){const int count=map_size(text(o,"map_id",32))*2;settings(o.at("settings"));const auto& all=array(o,"slots",8);slots(all,count);for(const auto& row:all)integer(object(row),"side",1,count);}
}
inline void battle(const json::value&v){const auto&o=object(v);keys(o,{"id","area_id","state","created_at","teams","format","revision","map","validity","settings","ranked","room_state","generation","engine_host_account_id"});id(o,"id");text(o,"area_id",64);text(o,"created_at",20);integer(o,"format",2,2);integer(o,"revision",1);settings(o.at("settings"));boolean(o,"ranked");id(o,"generation",true);id(o,"engine_host_account_id",true);
 const auto state=text(o,"state",16),room=text(o,"room_state",16,true);if(state!="draft"&&state!="running"&&state!="completed"&&state!="cancelled")invalid();if(!room.empty()&&room!="preparing"&&room!="running"&&room!="completed"&&room!="cancelled")invalid();text(o,"validity",32);
 const auto&m=object(o.at("map"));keys(m,{"id","name","scenario_id","size","sides"});const int size=map_size(text(m,"id",32));integer(m,"size",size,size);text(m,"name",80);text(m,"scenario_id",80);const auto&groups=array(m,"sides",2);if(groups.size()!=2)invalid();std::set<int>map_sides;for(const auto&g:groups){if(!g.is_array()||g.as_array().size()!=static_cast<std::size_t>(size))invalid();for(const auto&s:g.as_array())if(!s.is_int64()||s.as_int64()<1||s.as_int64()>size*2||!map_sides.insert(s.as_int64()).second)invalid();}
 const json::value expected=json::parse(size==2?"[[1,4],[2,3]]":size==3?"[[1,4,5],[2,3,6]]":"[[1,3,5,8],[2,4,6,7]]");if(groups!=expected.as_array())invalid();
 const auto&teams=array(o,"teams",2);if(teams.size()!=2)invalid();std::set<std::string>team_ids,accounts;std::set<int>seats;int ti=0;for(const auto&tv:teams){const auto&t=object(tv);keys(t,{"id","name","captain_id","approved","players","slots"});id(t,"id");id(t,"captain_id",true);if(!team_ids.insert(text(t,"id",36)).second)invalid();text(t,"name",40);boolean(t,"approved");const auto&ss=array(t,"slots",4);slots(ss,size);std::set<int>team_sides;for(const auto&sv:ss){const auto&so=object(sv);int side=integer(so,"side",1,size*2);if(std::find(groups[ti].as_array().begin(),groups[ti].as_array().end(),json::value(side))==groups[ti].as_array().end()||!seats.insert(side).second)invalid();team_sides.insert(side);}for(const auto&pv:array(t,"players",4)){const auto&p=object(pv);keys(p,{"id","username","side","ready","selection"});id(p,"id");if(!accounts.insert(text(p,"id",36)).second||!team_sides.erase(integer(p,"side",1,8)))invalid();text(p,"username",24);boolean(p,"ready");const int side=integer(p,"side",1,8);const auto found=std::find_if(ss.begin(),ss.end(),[side](const json::value& row){return integer(object(row),"side",1,8)==side;});if(found==ss.end())invalid();const auto& assigned=object(*found);const auto kind=text(assigned,"kind",8);if(kind!="open"&&kind!="reserved")invalid();if(kind=="reserved"&&text(assigned,"account_id",36)!=text(p,"id",36))invalid();if(p.at("ready").as_bool()&&p.at("selection").is_null())invalid();if(!p.at("selection").is_null())selection(p.at("selection"));}++ti;}
}
inline void response(const std::string&,const json::object&o){keys(o,{"battle"});battle(o.at("battle"));}
}
