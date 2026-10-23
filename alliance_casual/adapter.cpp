// SPDX-License-Identifier: GPL-2.0-or-later
#include "adapter.hpp"
#include "../alliance_bridge/unified_protocol.hpp"
#include <boost/asio.hpp>
#include <boost/beast.hpp>
#include <boost/json/src.hpp>
#include <boost/uuid/random_generator.hpp>
#include <boost/uuid/uuid_io.hpp>
#include <algorithm>
#include <fstream>
#include <limits>
#include <set>
#include <stdexcept>
namespace alliance_casual {
namespace json=boost::json; namespace asio=boost::asio; namespace http=boost::beast::http;
namespace wire=alliance::unified_protocol;
static void require_at(bool yes,int step){if(!yes)throw std::runtime_error("Unified multiplayer validation step "+std::to_string(step)+" failed.");}
#define require(condition) require_at((condition),__LINE__)
static std::string read_file(const std::string& path,std::size_t limit){std::ifstream f(path,std::ios::binary);require(bool(f));std::string s(limit+1,'\0');f.read(s.data(),static_cast<std::streamsize>(s.size()));s.resize(static_cast<std::size_t>(f.gcount()));require(!s.empty()&&s.size()<=limit);return s;}
static std::string str(const json::object&o,const char*k){return wire::text(o,k,200);}
static std::int64_t number(const json::object&o,const char*k){return wire::integer(o,k);}
static int scaled(std::int64_t base,std::int64_t level,std::int64_t percent){require(base>0&&level>0&&level<100000000);auto value=(base*(100+percent*(level-1))+50)/100;require(value>0&&value<=std::numeric_limits<int>::max());return static_cast<int>(value);}
adapter::adapter(const config&cfg){
 require(cfg["tls_enabled"].to_bool());
 auto settings=json::parse(read_file(cfg["alliance_runtime"].str()+"/config.json",65536)).as_object();
 const auto& service=settings.at("service").as_object();secret_=str(service,"bridge_secret");
 require(str(service,"host")=="127.0.0.1");auto port=number(service,"port");require(port>0&&port<65536);port_=static_cast<unsigned short>(port);
 require(cfg["alliance_backend_port"].to_int(18765)==port_);
 catalog_=json::parse(read_file(cfg["alliance_catalog"].str(),4194304)).as_object();
 require(str(catalog_,"version")=="unified-heroes-v1");
}
json::object adapter::call(const std::string& op,const json::object& body){
 asio::io_context io;asio::ip::tcp::socket socket(io);boost::beast::flat_buffer buffer;
 http::request<http::string_body> request{http::verb::post,"/internal/v1/casual/"+op,11};
 request.set(http::field::host,"127.0.0.1");request.set(http::field::authorization,"Bearer "+secret_);
 request.set(http::field::content_type,"application/json");request.body()=json::serialize(body);request.prepare_payload();
 http::response_parser<http::string_body> parser;parser.body_limit(262144);parser.header_limit(8192);
 bool complete=false;boost::system::error_code result;
 socket.async_connect({asio::ip::make_address("127.0.0.1"),port_},[&](auto ec){
  if(ec){result=ec;complete=true;return;}
  http::async_write(socket,request,[&](auto ec,std::size_t){if(ec){result=ec;complete=true;return;}
   http::async_read(socket,buffer,parser,[&](auto ec,std::size_t){result=ec;complete=true;});});});
 io.run_for(std::chrono::seconds(6));
 if(!complete){boost::system::error_code ignored;socket.cancel(ignored);socket.close(ignored);io.restart();io.run();require(false);}
 require(!result&&parser.get().result_int()==200);auto parsed=json::parse(parser.get().body());require(parsed.is_object());return parsed.as_object();
}
json::object adapter::admit(const std::string&ticket,const std::string&username){auto value=call("admit",{{"ticket",ticket},{"username",username}});require(str(value,"username")==username);str(value,"account_id");str(value,"database_generation");return value;}
room& adapter::create(int game){require(rooms_.find(game)==rooms_.end());room value;value.id=boost::uuids::to_string(boost::uuids::random_generator()());return rooms_.emplace(game,std::move(value)).first->second;}
room& adapter::get(int game){return rooms_.at(game);}
void adapter::remove(int game){rooms_.erase(game);}
void adapter::restore(int game,simple_wml::node&level){
 auto& state=get(game);auto* scenario=level.child("snapshot");if(!scenario)scenario=level.child("scenario");require(scenario);
 auto saved=level["alliance_casual_game_id"].to_string();if(saved.empty())saved=(*scenario)["alliance_casual_game_id"].to_string();
 if(!saved.empty()&&saved!=state.id){auto result=call("restore",{{"game_id",saved}});state.id=saved;state.restored=true;state.seats.clear();
  for(const auto& value:result.at("players").as_array()){const auto&p=value.as_object();seat row;row.account_id=str(p,"account_id");row.username=str(p,"username");wire::selection(p.at("selection"));row.selection=p.at("selection").as_object();state.seats.emplace(static_cast<int>(number(p,"side")),std::move(row));}}
 require(!level.child("snapshot")||state.restored);
 level.set_attr_dup("alliance_casual_game_id",state.id.c_str());scenario->set_attr_dup("alliance_casual_game_id",state.id.c_str());
}
void adapter::choose(int game,int side,const std::string&account,const std::string&username,const std::string&ticket){
 auto& state=get(game);require(!state.restored);auto response=call("hero",{{"ticket",ticket},{"account_id",account},{"game_id",state.id},{"side",side}});wire::selection(response.at("selection"));
 for(const auto& [number,s]:state.seats)require(number==side||s.account_id!=account);
 auto& value=state.seats[side];auto selection=response.at("selection").as_object();
 if(value.account_id!=account||value.selection!=selection){changed(game);value={account,username,selection,false};}
}
void adapter::changed(int game,bool reset_ready){auto&state=get(game);require(state.revision<std::numeric_limits<std::int64_t>::max());++state.revision;state.launch_revision=0;if(reset_ready)for(auto&[_,s]:state.seats)s.ready=false;}
void adapter::ready(int game,int side,const std::string&account,bool value){auto&state=get(game);auto&s=state.seats.at(side);require(s.account_id==account);s.ready=value;}
void adapter::freeze(int game){auto&state=get(game);json::array players;for(const auto&[side,s]:state.seats){require(s.ready);players.push_back(json::object{{"account_id",s.account_id},{"username",s.username},{"side",side},{"selection",s.selection}});}call("freeze",{{"game_id",state.id},{"players",players}});state.restored=true;}
void adapter::context(int game,simple_wml::document&output)const{const auto&state=rooms_.at(game);auto&n=output.root().add_child("alliance_game");n.set_attr_dup("id",state.id.c_str());n.set_attr("resume",state.restored?"yes":"no");if(state.individual){n.set_attr("individual_room","yes");n.set_attr_dup("room_revision",std::to_string(state.revision).c_str());}}
void adapter::selections(int game,simple_wml::document&output)const{const auto&state=rooms_.at(game);for(const auto&[side,s]:state.seats){auto&n=output.root().add_child("alliance_selection");n.set_attr_dup("game_id",state.id.c_str());n.set_attr_int("side",side);n.set_attr_dup("account_id",s.account_id.c_str());n.set_attr_dup("username",s.username.c_str());n.set_attr("ready",s.ready?"yes":"no");for(const auto*key:{"hero_id","form_id","unit_type"})n.set_attr_dup(key,str(s.selection,key).c_str());for(const auto*key:{"hero_level","hero_revision","unit_level"})n.set_attr_dup(key,std::to_string(number(s.selection,key)).c_str());}}
void adapter::validate_leader(const simple_wml::node& side,const seat& selected,bool restored)const{
 const auto&s=selected.selection;require(side["alliance_account_id"].to_string()==selected.account_id);
 for(const auto*key:{"hero_id","form_id"}){std::string attr="alliance_"+std::string(key);require(side[attr.c_str()].to_string()==str(s,key));}
 require(side["alliance_hero_level"].to_string()==std::to_string(number(s,"hero_level")));
 require(side["alliance_hero_revision"].to_string()==std::to_string(number(s,"hero_revision")));
 if(restored) {
  // Saved combat state keeps the frozen snapshot; a surviving leader still
  // must be the recorded hero/form. A fallen leader may be absent.
  for(const auto* tag:{"unit","leader"})for(const auto* unit:side.children(tag))if((*unit)["canrecruit"].to_bool()) {
   const auto* vars=unit->child("variables");require((*unit)["type"].to_string()==str(s,"unit_type")&&vars);
   require((*vars)["alliance_hero_id"].to_string()==str(s,"hero_id")&&(*vars)["alliance_form_id"].to_string()==str(s,"form_id")&&(*vars)["alliance_hero_level"].to_string()==std::to_string(number(s,"hero_level")));
  }
  return;
 }
 const auto&leaders=side.children("leader");require(leaders.size()==1);const auto&leader=*leaders[0];
 require(leader["type"].to_string()==str(s,"unit_type")&&!leader["random_traits"].to_bool(true)&&leader["canrecruit"].to_bool());
 require(leader.children("attack").empty()&&leader.children("abilities").empty()&&leader.children("advancement").empty());
 for(const auto*key:{"hitpoints","max_hitpoints","movement","max_moves","level","experience","max_experience","variation","attacks_left"})require(!leader.has_attr(key));
 const auto*vars=leader.child("variables");require(vars&&vars->no_children()&&vars->nattributes()==3);require((*vars)["alliance_hero_id"].to_string()==str(s,"hero_id")&&(*vars)["alliance_form_id"].to_string()==str(s,"form_id")&&(*vars)["alliance_hero_level"].to_string()==std::to_string(number(s,"hero_level")));
 const json::object*form=nullptr;for(const auto&v:catalog_.at("forms").as_array()){const auto&f=v.as_object();if(str(f,"id")==str(s,"form_id")&&str(f,"hero_id")==str(s,"hero_id")){form=&f;break;}}require(form&&str(*form,"unit_type")==str(s,"unit_type"));
 const auto*mods=leader.child("modifications");require(mods&&mods->one_child());const auto&objects=mods->children("object");require(objects.size()==1);const auto&object=*objects[0];require(object["id"].to_string()=="unified_hero_scaling"&&object["duration"].to_string()=="forever"&&object["silent"].to_bool());
 std::set<std::tuple<std::string,std::string,std::string,int,int>> attacks;for(const auto&a:form->at("attacks").as_array()){const auto&v=a.as_object();attacks.emplace(str(v,"name"),str(v,"type"),str(v,"range"),static_cast<int>(number(v,"number")),static_cast<int>(number(v,"damage")));}
 const auto&effects=object.children("effect");require(effects.size()==attacks.size()+1);const auto&hp=*effects[0];auto level=number(s,"hero_level");require(hp.no_children()&&hp.nattributes()==3);require(hp["apply_to"].to_string()=="hitpoints"&&hp["set_total"].to_int()==scaled(number(*form,"base_hitpoints"),level,2)&&hp["heal_full"].to_bool());
 require(object.nchildren()==static_cast<int>(effects.size()));
 require(object.nattributes()==3);
 require(mods->nattributes()==0);
 require(leader.nchildren()==static_cast<int>(attacks.size())+4);
 // Preserve scenario-authored event identities without accepting stat overrides.
 std::size_t attributes=3;
 for(const auto* key:{"id","name"}) if(leader.has_attr(key)) {
  const auto value=leader[key].to_string();require(!value.empty()&&value.size()<=256);++attributes;
 }
 if(leader.has_attr("gender")) {
  const auto value=leader["gender"].to_string();require(value=="male"||value=="female");++attributes;
 }
 require(leader.nattributes()==attributes);
 std::set<std::tuple<std::string,std::string,std::string,int,int>> seen;
 int previous_damage=std::numeric_limits<int>::max();
 for(std::size_t i=1;i<effects.size();++i){const auto&e=*effects[i];require(e.no_children()&&e.nattributes()==7&&e["damage"].to_int()<=previous_damage);previous_damage=e["damage"].to_int();auto key=std::make_tuple(e["name"].to_string(),e["type"].to_string(),e["range"].to_string(),e["number"].to_int(),e["damage"].to_int());require(e["apply_to"].to_string()=="attack"&&attacks.count(key)&&seen.insert(key).second&&e["set_damage"].to_int()==scaled(std::get<4>(key),level,1));}
}
}
