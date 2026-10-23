// SPDX-License-Identifier: GPL-2.0-or-later
#pragma once
#include <boost/json.hpp>
#include <map>
#include <cstdint>
#include <string>
#include "config.hpp"
#include "server/common/simple_wml.hpp"
namespace alliance_casual {
struct seat {std::string account_id, username; boost::json::object selection; bool ready=false;};
struct room {
 std::string id, layout, settings;
 bool restored=false, individual=false;
 std::int64_t revision=1, launch_revision=0;
 std::map<int,seat> seats;
};
class adapter {
public:
 explicit adapter(const config& cfg);
 boost::json::object admit(const std::string& ticket,const std::string& username);
 room& create(int game);
 room& get(int game);
 void remove(int game);
 void restore(int game,simple_wml::node& level);
 void choose(int game,int side,const std::string& account,const std::string& username,const std::string& ticket);
 void ready(int game,int side,const std::string& account,bool value);
 void freeze(int game);
 void validate_leader(const simple_wml::node& side,const seat& selected,bool restored) const;
 void context(int game,simple_wml::document& output) const;
 void selections(int game,simple_wml::document& output) const;
 void changed(int game, bool reset_ready=true);
private:
 boost::json::object call(const std::string& op,const boost::json::object& body);
 std::string secret_; unsigned short port_=18765;
 boost::json::object catalog_;
 std::map<int,room> rooms_;
};
}
