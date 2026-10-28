// SPDX-License-Identifier: GPL-2.0-or-later
// Separate account listener. It never reads the guest game socket or submits
// game results. All application operations have a fixed loopback destination.
#include <boost/asio.hpp>
#include <boost/asio/ssl.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/core/flat_buffer.hpp>
#include <boost/json/src.hpp>
#include "progression_protocol.hpp"
#include "unified_protocol.hpp"
#include "flexible_protocol.hpp"
#include "world_protocol.hpp"
#include <openssl/crypto.h>
#include <openssl/sha.h>
#include <openssl/x509v3.h>
#include <zlib.h>
#include <array>
#include <chrono>
#include <csignal>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <map>
#include <memory>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>
#ifdef _WIN32
#include <windows.h>
#endif

namespace {
namespace asio = boost::asio;
namespace ssl = asio::ssl;
namespace http = boost::beast::http;
namespace json = boost::json;
using tcp = asio::ip::tcp;
using Error = boost::system::error_code;
constexpr std::size_t max_frame = 65536, max_json = 262144;
constexpr unsigned max_connections = 32;
constexpr auto request_timeout = std::chrono::seconds(10);

[[noreturn]] void invalid() { throw std::runtime_error("Invalid account bridge input."); }
bool ascii_word(const std::string& value, std::size_t lo, std::size_t hi) {
    if(value.size() < lo || value.size() > hi) return false;
    for(unsigned char c : value)
        if(!((c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') ||
             (c >= '0' && c <= '9') || c == '_' || c == '-')) return false;
    return true;
}
bool uuid(const std::string& value) {
    if(value.size() != 36) return false;
    for(std::size_t i = 0; i < value.size(); ++i) {
        const char c = value[i];
        if(i == 8 || i == 13 || i == 18 || i == 23) { if(c != '-') return false; }
        else if(!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    }
    return true;
}
std::string directory_name(std::string value) {
    const auto first = value.find_first_not_of(' '), last = value.find_last_not_of(' ');
    if(first == std::string::npos) invalid();
    value = value.substr(first, last - first + 1);
    if(value.size() < 3 || value.size() > 40) invalid();
    for(std::size_t i = 0; i < value.size(); ++i) {
        const char c = value[i];
        const bool alnum = (c >= 'a' && c <= 'z') || (c >= 'A' && c <= 'Z') || (c >= '0' && c <= '9');
        if(!alnum && (i == 0 || (c != ' ' && c != '_' && c != '-'))) invalid();
    }
    return value;
}
bool directory_operation(const std::string& operation) {
    return operation == "areas" || operation == "teams" || operation == "my_team" ||
           operation == "create_team" || operation == "team_detail" ||
           operation == "my_applications" || operation == "team_applicants" ||
           operation == "apply_team" || operation == "withdraw_application" ||
           operation == "approve_application" || operation == "reject_application" ||
           operation == "application_decisions" || operation == "ack_decision" ||
           operation == "leave_team" || operation == "transfer_captain" || operation == "standings" ||
           operation == "battle_maps" || operation == "my_battles" || operation == "battle_detail" ||
           operation == "propose_battle" || operation == "approve_battle" || operation == "battle_ready" ||
           operation == "cancel_battle";
}
int battle_map_size(const std::string& id) {
    if(id == "isars-cross") return 2;
    if(id == "hexcake") return 3;
    if(id == "mokena-prairie") return 4;
    invalid();
}
bool request_id(const std::string& value) {
    if(value.size() != 32) return false;
    for(char c : value) if(!((c >= '0' && c <= '9') || (c >= 'a' && c <= 'f'))) return false;
    return true;
}
std::string text(const json::value& value, std::size_t maximum) {
    if(!value.is_string() || value.as_string().size() > maximum) invalid();
    return std::string(value.as_string());
}
void fields(const json::object& object, std::initializer_list<const char*> required,
            std::initializer_list<const char*> optional = {}) {
    for(auto key : required) if(!object.contains(key)) invalid();
    for(const auto& item : object) {
        bool known = false;
        for(auto key : required) if(item.key() == key) known = true;
        for(auto key : optional) if(item.key() == key) known = true;
        if(!known) invalid();
    }
}
// Boost's value parser retains the last duplicate key. Validate names before
// using the parsed tree so duplicate credentials/operations never get accepted.
class UniqueKeys {
    const std::string& input_;
    std::size_t at_ = 0;
    void space() { while(at_ < input_.size() && std::isspace(static_cast<unsigned char>(input_[at_]))) ++at_; }
    std::string string() {
        const auto start = at_++;
        while(at_ < input_.size()) {
            if(input_[at_] == '\\') { at_ += 2; continue; }
            if(input_[at_++] == '"') {
                auto item = json::parse(input_.substr(start, at_ - start));
                return std::string(item.as_string());
            }
        }
        invalid();
    }
    void value(unsigned depth) {
        if(depth > 8) invalid();
        space();
        if(at_ >= input_.size()) invalid();
        if(input_[at_] == '"') { string(); return; }
        if(input_[at_] == '{') {
            ++at_; space(); std::set<std::string> keys;
            if(input_[at_] == '}') { ++at_; return; }
            while(true) {
                space();
                if(input_[at_] != '"' || !keys.insert(string()).second) invalid();
                space(); if(input_[at_++] != ':') invalid();
                value(depth + 1); space();
                const char next = input_[at_++];
                if(next == '}') return;
                if(next != ',') invalid();
            }
        }
        if(input_[at_] == '[') {
            ++at_; space();
            if(input_[at_] == ']') { ++at_; return; }
            while(true) {
                value(depth + 1); space();
                const char next = input_[at_++];
                if(next == ']') return;
                if(next != ',') invalid();
            }
        }
        while(at_ < input_.size() && input_[at_] != ',' && input_[at_] != '}' &&
              input_[at_] != ']' && !std::isspace(static_cast<unsigned char>(input_[at_]))) ++at_;
    }
public:
    explicit UniqueKeys(const std::string& input) : input_(input) {}
    void check() { value(0); space(); if(at_ != input_.size()) invalid(); }
};
json::value parse_json(const std::string& input) {
    if(input.empty() || input.size() > max_json) invalid();
    json::parse_options options; options.max_depth = 12;
    const auto value = json::parse(input, {}, options); // Syntax/UTF-8 checked first.
    UniqueKeys(input).check();
    return value;
}
std::string regular_file(const std::filesystem::path& path, std::size_t limit) {
    if(!path.is_absolute()) invalid();
    for(auto current = path; !current.empty(); current = current.parent_path()) {
        if(std::filesystem::is_symlink(std::filesystem::symlink_status(current))) invalid();
#ifdef _WIN32
        const auto attributes = GetFileAttributesW(current.c_str());
        if(attributes == INVALID_FILE_ATTRIBUTES || attributes & FILE_ATTRIBUTE_REPARSE_POINT) invalid();
#endif
        if(current == current.parent_path()) break;
    }
    if(!std::filesystem::is_regular_file(path) || std::filesystem::hard_link_count(path) != 1 ||
       std::filesystem::file_size(path) > limit) invalid();
    std::ifstream stream(path, std::ios::binary);
    std::string data(limit + 1, '\0');
    stream.read(data.data(), static_cast<std::streamsize>(data.size()));
    const auto size = stream.gcount();
    if(stream.bad() || size < 1 || static_cast<std::size_t>(size) > limit) invalid();
    data.resize(static_cast<std::size_t>(size));
    return data;
}
std::string inflate_frame(const std::vector<unsigned char>& bytes) {
    std::array<unsigned char, max_json + 1> output{};
    z_stream stream{};
    if(inflateInit2(&stream, MAX_WBITS + 16) != Z_OK) invalid();
    stream.next_in = const_cast<unsigned char*>(bytes.data());
    stream.avail_in = static_cast<uInt>(bytes.size());
    stream.next_out = output.data(); stream.avail_out = output.size();
    const int status = inflate(&stream, Z_FINISH);
    const auto size = stream.total_out;
    const bool valid = status == Z_STREAM_END && stream.avail_in == 0 && size <= max_json && size > 0;
    inflateEnd(&stream);
    if(!valid) invalid();
    return std::string(reinterpret_cast<const char*>(output.data()), size);
}
std::vector<unsigned char> compress_text_frame(const std::string& input) {
    if(input.empty() || input.size() > max_json) invalid();
    std::vector<unsigned char> output(max_frame + 4);
    z_stream stream{};
    if(deflateInit2(&stream, Z_DEFAULT_COMPRESSION, Z_DEFLATED, MAX_WBITS + 16, 8, Z_DEFAULT_STRATEGY) != Z_OK) invalid();
    stream.next_in = reinterpret_cast<unsigned char*>(const_cast<char*>(input.data()));
    stream.avail_in = input.size();
    stream.next_out = output.data() + 4; stream.avail_out = max_frame;
    const int status = deflate(&stream, Z_FINISH);
    const auto size = stream.total_out;
    deflateEnd(&stream);
    if(status != Z_STREAM_END || size == 0 || size > max_frame) invalid();
    for(unsigned i = 0; i < 4; ++i) output[i] = static_cast<unsigned char>(size >> (24 - 8 * i));
    output.resize(size + 4);
    return output;
}
std::vector<unsigned char> compress_frame(const json::value& value) { return compress_text_frame(json::serialize(value)); }
std::size_t utf8_characters(const std::string& value) {
    std::size_t result = 0;
    for(unsigned char c : value) if((c & 0xc0) != 0x80) ++result;
    return result;
}
struct Request {
    std::string id, operation, token, body, target;
    unsigned protocol = 4;
    http::verb method = http::verb::post;
};
Request account_request(const std::vector<unsigned char>& bytes) {
    auto value = parse_json(inflate_frame(bytes));
    if(!value.is_object()) invalid();
    const auto& root = value.as_object();
    fields(root, {"v", "id", "op", "body"}, {"token"});
    if(!root.at("v").is_int64() || (root.at("v").as_int64() != 4 && root.at("v").as_int64() != 3 && root.at("v").as_int64() != 2)) invalid();
    Request result;
    result.protocol = static_cast<unsigned>(root.at("v").as_int64());
    result.id = text(root.at("id"), 32); if(!request_id(result.id)) invalid();
    result.operation = text(root.at("op"), 24);
    if(!root.at("body").is_object()) invalid();
    if(result.protocol < 4) {
        // Recognize only the bounded envelope so the previous client receives
        // an explicit upgrade rejection. Never interpret or dispatch its body.
        if(!ascii_word(result.operation, 1, 24)) invalid();
        if(root.contains("token") && !ascii_word(text(root.at("token"), 43), 43, 43)) invalid();
        return result;
    }
    const auto& body = root.at("body").as_object();
    if(result.operation == "register" || result.operation == "login") {
        if(root.contains("token")) invalid();
        fields(body, {"username", "password"});
        const auto username = text(body.at("username"), 24);
        if(!ascii_word(username, 3, 24) || username.find('-') != std::string::npos) invalid();
        const auto password = text(body.at("password"), 512);
        const auto length = utf8_characters(password);
        if(length < (result.operation == "register" ? 12U : 1U) || length > 128 || password.find('\0') != std::string::npos) invalid();
    } else if(result.operation == "me" || result.operation == "logout") {
        fields(body, {});
        if(!root.contains("token")) invalid();
        result.token = text(root.at("token"), 43);
        if(!ascii_word(result.token, 43, 43)) invalid();
        if(result.operation == "me") result.method = http::verb::get;
    } else if(alliance::world_protocol::operation(result.operation)) {
        if(!root.contains("token")) invalid();
        result.token=text(root.at("token"),43);
        if(!ascii_word(result.token,43,43)) invalid();
        alliance::world_protocol::request(result.operation,body);
    } else if(alliance::flexible_protocol::operation(result.operation)) {
        if(!root.contains("token")) invalid();
        result.token=text(root.at("token"),43);
        if(!ascii_word(result.token,43,43)) invalid();
        alliance::flexible_protocol::request(result.operation,body);
    } else if(alliance::unified_protocol::operation(result.operation)) {
        if(!root.contains("token")) invalid();
        result.token=text(root.at("token"),43);
        if(!ascii_word(result.token,43,43)) invalid();
        alliance::unified_protocol::request(result.operation,body);
    } else if(alliance::progression_protocol::operation(result.operation)) {
        if(!root.contains("token")) invalid();
        result.token = text(root.at("token"), 43);
        if(!ascii_word(result.token,43,43)) invalid();
        alliance::progression_protocol::request(result.operation,body);
    } else if(directory_operation(result.operation)) {
        if(!root.contains("token")) invalid();
        result.token = text(root.at("token"), 43);
        if(!ascii_word(result.token, 43, 43)) invalid();
        if(result.operation == "areas" || result.operation == "my_applications" || result.operation == "my_battles") fields(body, {"after"});
        else if(result.operation == "teams") fields(body, {"area_id", "after"});
        else if(result.operation == "standings" || result.operation == "battle_maps") fields(body, {"area_id"});
        else if(result.operation == "battle_detail" || result.operation == "approve_battle" ||
                result.operation == "cancel_battle") fields(body, {"battle_id"});
        else if(result.operation == "battle_ready") fields(body, {"battle_id", "ready"});
        else if(result.operation == "propose_battle") fields(body, {"team_id", "opponent_team_id", "map_id", "lineups"});
        else if(result.operation == "leave_team") fields(body, {"team_id", "allow_archive"});
        else if(result.operation == "my_team" || result.operation == "application_decisions") fields(body, {});
        else if(result.operation == "ack_decision") fields(body, {"decision_id"});
        else if(result.operation == "create_team") fields(body, {"name", "area_id"});
        else if(result.operation == "team_applicants") fields(body, {"team_id", "after"});
        else if(result.operation == "approve_application" || result.operation == "reject_application" ||
                result.operation == "transfer_captain")
            fields(body, {"team_id", "account_id"});
        else fields(body, {"team_id"});
        if(body.contains("after")) {
            const auto after = text(body.at("after"), 64);
            if(!after.empty() && !(result.operation == "areas" ? ascii_word(after, 1, 64) : uuid(after))) invalid();
        }
        if(body.contains("area_id") && !ascii_word(text(body.at("area_id"), 64), 1, 64)) invalid();
        if(body.contains("team_id") && !uuid(text(body.at("team_id"), 36))) invalid();
        if(body.contains("battle_id") && !uuid(text(body.at("battle_id"), 36))) invalid();
        if(body.contains("ready") && !body.at("ready").is_bool()) invalid();
        if(result.operation == "propose_battle") {
            if(!uuid(text(body.at("opponent_team_id"), 36)) || body.at("team_id") == body.at("opponent_team_id")) invalid();
            const auto size = battle_map_size(text(body.at("map_id"), 32));
            if(!body.at("lineups").is_array() || body.at("lineups").as_array().size() != 2) invalid();
            std::set<std::string> teams, players;
            for(const auto& value : body.at("lineups").as_array()) {
                if(!value.is_object()) invalid();
                const auto& lineup = value.as_object();
                fields(lineup, {"team_id", "account_ids"});
                const auto team_id = text(lineup.at("team_id"), 36);
                if(!uuid(team_id) || !teams.insert(team_id).second ||
                   (lineup.at("team_id") != body.at("team_id") && lineup.at("team_id") != body.at("opponent_team_id")) ||
                   !lineup.at("account_ids").is_array() || lineup.at("account_ids").as_array().size() != static_cast<std::size_t>(size)) invalid();
                for(const auto& player : lineup.at("account_ids").as_array()) {
                    const auto id = text(player, 36);
                    if(!uuid(id) || !players.insert(id).second) invalid();
                }
            }
        }
        if(body.contains("allow_archive") && !body.at("allow_archive").is_bool()) invalid();
        if(body.contains("account_id") && !uuid(text(body.at("account_id"), 36))) invalid();
        if(body.contains("decision_id") && !uuid(text(body.at("decision_id"), 36))) invalid();
        if(body.contains("name")) directory_name(text(body.at("name"), 64));
    } else invalid();
    result.body = json::serialize(body);
    if(alliance::world_protocol::operation(result.operation)) {
        result.target=result.operation=="world_query" ? "/internal/v1/world/query" : "/internal/v1/world/command";
        return result;
    } else if(alliance::flexible_protocol::operation(result.operation)) {
        result.target="/internal/v1/team-directory/"+result.operation;return result;
    } else if(alliance::unified_protocol::operation(result.operation)) {
        result.target="/internal/v1/product/"+result.operation;return result;
    }
    if(alliance::progression_protocol::operation(result.operation)) {
        result.target = alliance::progression_protocol::target(result.operation);
        return result;
    }
    result.target = directory_operation(result.operation)
        ? "/internal/v1/team-directory/" + result.operation : "/internal/v1/" + result.operation;
    return result;
}
json::object safe_error(const std::string& id, unsigned status) {
    const char* code = "service_unavailable";
    const char* message = "The account service is unavailable. Check the server, then try again.";
    if(status == 400) { code = "invalid_request"; message = "The account request is invalid."; }
    else if(status == 401) { code = "invalid_credentials"; message = "Sign in failed or the session expired. Sign in again."; }
    else if(status == 403) { code = "forbidden"; message = "This account operation is not permitted."; }
    else if(status == 409) { code = "conflict"; message = "The username is unavailable or the account request conflicts with current state."; }
    else if(status == 429) { code = "rate_limited"; message = "Too many attempts. Wait before trying again."; }
    else status = 503;
    return {{"v", 4}, {"id", id}, {"ok", false}, {"status", status},
            {"data", {{"code", code}, {"message", message}}}};
}
json::object public_account(const json::value& value) {
    if(!value.is_object()) invalid();
    const auto& source=value.as_object();
    json::object result{{"id",source.at("_id")},{"username",source.at("username")},
        {"database_generation",source.at("database_generation")},{"heroes",source.at("heroes")}};
    alliance::unified_protocol::profile(result);
    return result;
}
std::int64_t directory_integer(const json::object& object, const char* key,
                               std::int64_t minimum, std::int64_t maximum = 2147483647) {
    const auto& value = object.at(key);
    if(!value.is_int64() || value.as_int64() < minimum || value.as_int64() > maximum) invalid();
    return value.as_int64();
}
std::string directory_identifier(const json::value& value, bool is_uuid = false) {
    const auto result = text(value, 64);
    if(is_uuid ? !uuid(result) : !ascii_word(result, 1, 64)) invalid();
    return result;
}
std::string directory_display_name(const json::value& value) {
    const auto result = text(value, 40);
    if(directory_name(result) != result) invalid();
    return result;
}
std::string decision_timestamp(const json::value& value) {
    const auto stamp = text(value, 20);
    if(stamp.size() != 20) invalid();
    const std::string shape = "0000-00-00T00:00:00Z";
    for(std::size_t i = 0; i < shape.size(); ++i) {
        if(shape[i] == '0') { if(stamp[i] < '0' || stamp[i] > '9') invalid(); }
        else if(stamp[i] != shape[i]) invalid();
    }
    const int year = std::stoi(stamp.substr(0, 4)), month = std::stoi(stamp.substr(5, 2)),
              day = std::stoi(stamp.substr(8, 2));
    if(year < 1 || month < 1 || month > 12 || std::stoi(stamp.substr(11, 2)) > 23 ||
       std::stoi(stamp.substr(14, 2)) > 59 || std::stoi(stamp.substr(17, 2)) > 59) invalid();
    const int days[] = {31, 28 + (year % 4 == 0 && (year % 100 != 0 || year % 400 == 0)),
                        31, 30, 31, 30, 31, 31, 30, 31, 30, 31};
    if(day < 1 || day > days[month - 1]) invalid();
    return stamp;
}
json::object public_team_summary(const json::object& team, bool detail) {
    if(detail) fields(team, {"id", "name", "area_id", "area_name", "captain_id", "level",
                            "experience", "rating", "capacity", "members"});
    else fields(team, {"id", "name", "area_id", "captain_id", "level", "experience", "rating", "member_count"});
    json::object result{{"id", directory_identifier(team.at("id"), true)},
                        {"name", directory_display_name(team.at("name"))},
                        {"area_id", directory_identifier(team.at("area_id"))},
                        {"captain_id", directory_identifier(team.at("captain_id"), true)},
                        {"level", directory_integer(team, "level", 1)},
                        {"experience", directory_integer(team, "experience", 0)},
                        {"rating", directory_integer(team, "rating", -2147483647 - 1LL)}};
    if(!detail) result["member_count"] = directory_integer(team, "member_count", 1, 8);
    return result;
}
json::object public_member(const json::value& value) {
    if(!value.is_object()) invalid();
    const auto& member=value.as_object();fields(member,{"id","username","hero_count"});
    const auto id=directory_identifier(member.at("id"),true), username=text(member.at("username"),24);
    if(!ascii_word(username,3,24)||username.find('-')!=std::string::npos) invalid();
    return {{"id",id},{"username",username},{"hero_count",directory_integer(member,"hero_count",0,256)}};
}
json::object public_team_detail(const json::value& value) {
    if(!value.is_object()) invalid();
    const auto& team = value.as_object();
    auto result = public_team_summary(team, true);
    result["area_name"] = directory_display_name(team.at("area_name"));
    result["capacity"] = directory_integer(team, "capacity", 8, 8);
    if(!team.at("members").is_array()) invalid();
    const auto& source = team.at("members").as_array();
    if(source.empty() || source.size() > 8) invalid();
    std::set<std::string> ids;
    json::array members;
    for(const auto& item : source) {
        auto member = public_member(item);
        const auto id = text(member.at("id"), 36);
        if(!ids.insert(id).second) invalid();
        members.emplace_back(std::move(member));
    }
    if(!ids.count(text(result.at("captain_id"), 36))) invalid();
    result["members"] = std::move(members);
    return result;
}
json::object directory_error(const Request& request, unsigned status, const std::string& body) {
    const char* code = "service_unavailable";
    const char* message = "The Alliance service is unavailable. Refresh your team or application list before retrying a change.";
    if(status == 401) { code = "invalid_session"; message = "Your session has expired. Please log in again."; }
    else if(status == 403) { code = "forbidden"; message = "This team operation is not permitted."; }
    else if(status == 404) { code = "not_found"; message = "The selected team, area or application decision is no longer available. Refresh the list."; }
    else if(status == 400) { code = "invalid_input"; message = "Check the selected area, team or player."; }
    else if(status == 429) { code = "rate_limited"; message = "Too many requests. Wait before trying again."; }
    else if(status == 409) {
        // Read only a known error code. Never relay backend messages, details,
        // connection strings, secrets or arbitrary exception content.
        const auto value = parse_json(body);
        if(!value.is_object() || !value.as_object().at("error").is_object()) invalid();
        const auto source = text(value.as_object().at("error").as_object().at("code"), 64);
        if(source == "already_member") { code = "already_member"; message = "This player already belongs to a team. Refresh the team and applications."; }
        else if(source == "busy") { code = "busy"; message = "The active progression game must finish before this team change."; }
        else if(source == "invalid_input") { code = "invalid_input"; message = "Check the team name and selected area, team or player."; }
        else if(source == "capacity") { code = "capacity"; message = "The team or its application list is full."; }
        else if(source == "not_requested") { code = "not_requested"; message = "This application is no longer pending. Refresh the applications."; }
        else if(source == "captain_transfer_required") { code = "captain_transfer_required"; message = "Transfer captaincy to another member before leaving the team."; }
        else if(source == "not_member") { code = "not_member"; message = "The selected player is no longer a member. Refresh My team."; }
        else if(source == "planning_exists") { code = "planning_exists"; message = "One of these teams already has a planned battle. Inspect the plans before proposing another."; }
        else if(source == "invalid_map") { code = "invalid_map"; message = "Choose a map approved for this area."; }
        else if(source == "invalid_lineup") { code = "invalid_lineup"; message = "Choose the required distinct current members for each team."; }
        else if(source == "different_area") { code = "different_area"; message = "Both teams must belong to the same area."; }
        else if(source == "stale_proposal") { code = "stale_proposal"; message = "This battle plan changed or is unavailable. Inspect it before approving or becoming ready."; }
        else if(source == "advancement_required") { code = "advancement_required"; message = "A selected player must choose their available leader advancement before preparing this battle."; }
        else if(source == "approval_required") { code = "approval_required"; message = "Both current captains must explicitly approve this battle plan first."; }
        else if(source == "invalid_state") { code = "invalid_state"; message = "This operation requires a planned battle. Refresh the plan."; }
        else if(source == "suspended") { code = "forbidden"; message = "A required player is unavailable for this operation."; status = 403; }
        else if(source == "conflict") { code = "conflict"; message = "The team name or membership changed. Refresh My team before another change."; }
        else status = 503;
    } else status = 503;
    return {{"v", 4}, {"id", request.id}, {"ok", false}, {"status", status},
            {"data", {{"code", code}, {"message", message}}}};
}
json::object public_battle_map(const json::value& value) {
    if(!value.is_object()) invalid();
    const auto& source = value.as_object();
    fields(source, {"id", "name", "scenario_id", "size", "sides"});
    const auto id = text(source.at("id"), 32);
    const auto size = battle_map_size(id);
    const char* name = size == 2 ? "Isar's Cross" : size == 3 ? "Hexcake" : "Mokena Prairie";
    const char* scenario = size == 2 ? "multiplayer_Isars_Cross" : size == 3 ? "multiplayer_Hexcake" : "multiplayer_8p_Mokena_Prairie";
    const json::array sides = size == 2 ? json::array{json::array{1, 4}, json::array{2, 3}} :
        size == 3 ? json::array{json::array{1, 4, 5}, json::array{2, 3, 6}} :
                    json::array{json::array{1, 3, 5, 8}, json::array{2, 4, 6, 7}};
    if(text(source.at("name"), 32) != name || text(source.at("scenario_id"), 64) != scenario ||
       directory_integer(source, "size", 2, 4) != size || source.at("sides") != sides) invalid();
    return {{"id", id}, {"name", name}, {"scenario_id", scenario}, {"size", size}, {"sides", sides}};
}
json::object public_battle(const json::value& value, bool detail) {
    if(detail && value.is_object() && value.as_object().contains("format")) {
        alliance::flexible_protocol::battle(value); return value.as_object();
    }

    if(!value.is_object()) invalid();
    const auto& source = value.as_object();
    if(detail) fields(source, {"id", "area_id", "state", "created_at", "map", "validity", "teams"});
    else fields(source, {"id", "area_id", "state", "created_at", "map_id", "teams"});
    const auto state = text(source.at("state"), 9);
    if(state != "draft" && state != "running" && state != "completed" && state != "cancelled") invalid();
    json::object result{{"id", directory_identifier(source.at("id"), true)},
        {"area_id", directory_identifier(source.at("area_id"))}, {"state", state},
        {"created_at", decision_timestamp(source.at("created_at"))}};
    json::object map;
    if(detail) {
        map = public_battle_map(source.at("map"));
        result["map"] = map;
        const auto validity = text(source.at("validity"), 24);
        const std::set<std::string> allowed{"valid", "roster_changed", "area_changed", "map_unavailable",
            "leader_changed", "player_unavailable", "team_unavailable", "busy", "rules_changed"};
        if(!allowed.count(validity)) invalid();
        result["validity"] = validity;
    } else {
        const auto id = text(source.at("map_id"), 32);
        battle_map_size(id);
        result["map_id"] = id;
    }
    if(!source.at("teams").is_array() || source.at("teams").as_array().size() != 2) invalid();
    json::array teams;
    std::set<std::string> team_ids, player_ids;
    for(const auto& value : source.at("teams").as_array()) {
        if(!value.is_object()) invalid();
        const auto& team = value.as_object();
        if(detail) fields(team, {"id", "name", "captain_id", "approved", "players"});
        else fields(team, {"id", "name"});
        const auto id = directory_identifier(team.at("id"), true);
        if(!team_ids.insert(id).second) invalid();
        json::object entry{{"id", id}, {"name", directory_display_name(team.at("name"))}};
        if(detail) {
            const auto captain = text(team.at("captain_id"), 36);
            if((!captain.empty() && !uuid(captain)) || !team.at("approved").is_bool() ||
               (captain.empty() && team.at("approved").as_bool()) || !team.at("players").is_array() ||
               team.at("players").as_array().size() != static_cast<std::size_t>(map.at("size").as_int64())) invalid();
            entry["captain_id"] = captain;
            entry["approved"] = team.at("approved");
            json::array players;
            for(const auto& item : team.at("players").as_array()) {
                if(!item.is_object()) invalid();
                const auto& player = item.as_object();
                fields(player, {"id", "username", "selection", "side", "ready"});
                const auto account_id=directory_identifier(player.at("id"),true), username=text(player.at("username"),24);
                if(!ascii_word(username,3,24)) invalid();
                if(!player.at("selection").is_null()) alliance::unified_protocol::selection(player.at("selection"));
                else if(player.at("ready").is_bool()&&player.at("ready").as_bool()) invalid();
                json::object public_player{{"id",account_id},{"username",username},{"selection",player.at("selection")}};
                if(!player_ids.insert(text(public_player.at("id"), 36)).second || !player.at("ready").is_bool() ||
                   directory_integer(player, "side", 1, 8) != map.at("sides").as_array()[teams.size()].as_array()[players.size()].as_int64()) invalid();
                public_player["side"] = player.at("side");
                public_player["ready"] = player.at("ready");
                players.emplace_back(std::move(public_player));
            }
            entry["players"] = std::move(players);
        }
        teams.emplace_back(std::move(entry));
    }
    result["teams"] = std::move(teams);
    return result;
}
json::object directory_data(const Request& request, const json::object& root) {
    const auto body = parse_json(request.body).as_object();
    if(request.operation == "battle_maps") {
        fields(root, {"area_id", "maps"});
        const auto area_id = directory_identifier(root.at("area_id"));
        if(root.at("area_id") != body.at("area_id") || !root.at("maps").is_array() || root.at("maps").as_array().size() > 3) invalid();
        json::array maps;
        std::set<std::string> ids;
        for(const auto& value : root.at("maps").as_array()) {
            auto map = public_battle_map(value);
            if(!ids.insert(text(map.at("id"), 32)).second) invalid();
            maps.emplace_back(std::move(map));
        }
        return {{"area_id", area_id}, {"maps", std::move(maps)}};
    }
    if(request.operation == "my_battles") {
        fields(root, {"battles", "next"});
        if(!root.at("battles").is_array() || root.at("battles").as_array().size() > 20) invalid();
        json::array battles;
        std::string previous = text(body.at("after"), 36);
        for(const auto& value : root.at("battles").as_array()) {
            auto battle = public_battle(value, false);
            const auto id = text(battle.at("id"), 36);
            if(id <= previous) invalid();
            previous = id;
            battles.emplace_back(std::move(battle));
        }
        const auto next = text(root.at("next"), 36);
        if(!next.empty() && (battles.size() != 20 || next != previous)) invalid();
        return {{"battles", std::move(battles)}, {"next", next}};
    }
    if(request.operation == "battle_detail" || request.operation == "propose_battle" ||
       request.operation == "approve_battle" || request.operation == "battle_ready" || request.operation == "cancel_battle") {
        fields(root, {"battle"});
        auto battle = public_battle(root.at("battle"), true);
        if(request.operation != "propose_battle" && battle.at("id") != body.at("battle_id")) invalid();
        if((request.operation == "approve_battle" || request.operation == "battle_ready") && battle.at("state") != "draft") invalid();
        if(request.operation == "approve_battle" && battle.at("validity") != "valid") invalid();
        if(request.operation == "battle_ready" && body.at("ready").as_bool()) {
            if(battle.at("validity") != "valid") invalid();
            for(const auto& team : battle.at("teams").as_array())
                if(!team.as_object().at("approved").as_bool()) invalid();
        }
        if(request.operation == "cancel_battle" && battle.at("state") != "cancelled") invalid();
        if(request.operation == "propose_battle") {
            const auto& teams = battle.at("teams").as_array();
            if(battle.at("state") != "draft" || battle.at("validity") != "valid" ||
               battle.at("map").as_object().at("id") != body.at("map_id") ||
               teams[0].as_object().at("id") != body.at("team_id") || teams[1].as_object().at("id") != body.at("opponent_team_id")) invalid();
            for(const auto& team : teams) {
                if(team.as_object().at("approved").as_bool()) invalid();
                for(const auto& lineup : body.at("lineups").as_array()) {
                    if(lineup.as_object().at("team_id") != team.as_object().at("id")) continue;
                    const auto& players = team.as_object().at("players").as_array();
                    const auto& ids = lineup.as_object().at("account_ids").as_array();
                    for(std::size_t i = 0; i < players.size(); ++i)
                        if(players[i].as_object().at("id") != ids[i] || players[i].as_object().at("ready").as_bool()) invalid();
                }
            }
        }
        return {{"battle", std::move(battle)}};
    }
    if(request.operation == "standings") {
        fields(root, {"area_id", "teams", "has_more"});
        const auto area_id = directory_identifier(root.at("area_id"));
        if(area_id != text(body.at("area_id"), 64) || !root.at("has_more").is_bool() ||
           !root.at("teams").is_array() || root.at("teams").as_array().size() > 20) invalid();
        json::array teams;
        std::set<std::string> ids;
        std::string previous_id;
        std::int64_t previous_rating = 0;
        for(const auto& value : root.at("teams").as_array()) {
            if(!value.is_object()) invalid();
            auto team = public_team_summary(value.as_object(), false);
            const auto id = text(team.at("id"), 36);
            const auto rating = directory_integer(team, "rating", -2147483647 - 1LL);
            if(team.at("area_id") != root.at("area_id") || !ids.insert(id).second ||
               (!teams.empty() && (rating > previous_rating ||
                  (rating == previous_rating && id <= previous_id)))) invalid();
            previous_id = id;
            previous_rating = rating;
            teams.emplace_back(std::move(team));
        }
        if(root.at("has_more").as_bool() && teams.size() != 20) invalid();
        return {{"area_id", area_id}, {"teams", std::move(teams)}, {"has_more", root.at("has_more")}};
    }
    if(request.operation == "leave_team") {
        fields(root, {"team_id", "account_id", "status", "archived"});
        const auto team_id = directory_identifier(root.at("team_id"), true);
        const auto account_id = directory_identifier(root.at("account_id"), true);
        if(team_id != text(body.at("team_id"), 36) || text(root.at("status"), 4) != "left" ||
           !root.at("archived").is_bool() ||
           (root.at("archived").as_bool() && !body.at("allow_archive").as_bool())) invalid();
        return {{"team_id", team_id}, {"account_id", account_id}, {"status", "left"},
                {"archived", root.at("archived")}};
    }
    if(request.operation == "application_decisions") {
        fields(root, {"decisions"});
        if(!root.at("decisions").is_array() || root.at("decisions").as_array().size() > 50) invalid();
        std::set<std::string> ids;
        json::array decisions;
        for(const auto& value : root.at("decisions").as_array()) {
            if(!value.is_object()) invalid();
            const auto& notice = value.as_object();
            fields(notice, {"id", "team_id", "team_name", "status", "created_at", "unread"});
            const auto id = directory_identifier(notice.at("id"), true);
            const auto status = text(notice.at("status"), 8);
            if(!ids.insert(id).second || (status != "approved" && status != "rejected") ||
               !notice.at("unread").is_bool()) invalid();
            decisions.emplace_back(json::object{{"id", id},
                {"team_id", directory_identifier(notice.at("team_id"), true)},
                {"team_name", directory_display_name(notice.at("team_name"))}, {"status", status},
                {"created_at", decision_timestamp(notice.at("created_at"))}, {"unread", notice.at("unread")}});
        }
        return {{"decisions", std::move(decisions)}};
    }
    if(request.operation == "ack_decision") {
        fields(root, {"decision_id", "status"});
        const auto id = directory_identifier(root.at("decision_id"), true);
        if(id != text(body.at("decision_id"), 36) || text(root.at("status"), 4) != "read") invalid();
        return {{"decision_id", id}, {"status", "read"}};
    }
    if(request.operation == "areas" || request.operation == "teams" || request.operation == "my_applications" ||
       request.operation == "team_applicants") {
        const bool areas = request.operation == "areas";
        const bool applicants = request.operation == "team_applicants";
        const char* key = areas ? "areas" : applicants ? "applicants" : "teams";
        if(applicants) {
            fields(root, {"team_id", key, "next"});
            if(directory_identifier(root.at("team_id"), true) != text(body.at("team_id"), 36)) invalid();
        } else fields(root, {key, "next"});
        if(!root.at(key).is_array() || root.at(key).as_array().size() > 20) invalid();
        std::string previous = text(body.at("after"), 64);
        json::array records;
        for(const auto& item : root.at(key).as_array()) {
            if(!item.is_object()) invalid();
            const auto& source = item.as_object();
            json::object entry;
            if(areas) {
                fields(source, {"id", "name"});
                entry = {{"id", directory_identifier(source.at("id"))},
                         {"name", directory_display_name(source.at("name"))}};
            } else if(applicants) {
                entry = public_member(item);
            } else {
                entry = public_team_summary(source, false);
                if(request.operation == "teams" && entry.at("area_id") != body.at("area_id")) invalid();
            }
            const auto id = text(entry.at("id"), 64);
            if(id <= previous) invalid();
            previous = id;
            records.emplace_back(std::move(entry));
        }
        const auto next = text(root.at("next"), 64);
        if(!next.empty() && (records.size() != 20 || next != previous)) invalid();
        json::object result{{key, std::move(records)}, {"next", next}};
        if(applicants) result["team_id"] = root.at("team_id");
        return result;
    }
    const char* acknowledgment = request.operation == "apply_team" ? "applied" :
        request.operation == "withdraw_application" ? "withdrawn" :
        request.operation == "approve_application" ? "approved" :
        request.operation == "transfer_captain" ? "transferred" :
        request.operation == "reject_application" ? "rejected" : nullptr;
    if(acknowledgment) {
        fields(root, {"team_id", "account_id", "status"});
        const auto team_id = directory_identifier(root.at("team_id"), true);
        const auto account_id = directory_identifier(root.at("account_id"), true);
        if(team_id != text(body.at("team_id"), 36) || text(root.at("status"), 16) != acknowledgment ||
           (body.contains("account_id") && account_id != text(body.at("account_id"), 36))) invalid();
        return {{"team_id", team_id}, {"account_id", account_id}, {"status", acknowledgment}};
    }
    fields(root, {"team"});
    if(request.operation == "my_team" && root.at("team").is_null()) return {{"team", nullptr}};
    auto team = public_team_detail(root.at("team"));
    if(request.operation == "team_detail" && team.at("id") != body.at("team_id")) invalid();
    if(request.operation == "create_team" && (team.at("area_id") != body.at("area_id") ||
       text(team.at("name"), 40) != directory_name(text(body.at("name"), 64)))) invalid();
    return {{"team", std::move(team)}};
}
json::value account_response(const Request& request, unsigned status, const std::string& body) {
    const unsigned expected = request.operation == "publish_plan" || request.operation == "register" || request.operation == "create_team" ||
                              request.operation == "propose_battle" ? 201 : 200;
    const bool world=alliance::world_protocol::operation(request.operation);
    const bool unified=alliance::unified_protocol::operation(request.operation);
    const bool flex=alliance::flexible_protocol::operation(request.operation);
    const bool progression = alliance::progression_protocol::operation(request.operation);
    if((progression||unified||flex||world) && status != expected) {
        if(status==401||status>=500) return safe_error(request.id,status);
        const auto parsed = parse_json(body);
        if(!parsed.is_object()||!parsed.as_object().contains("error")||!parsed.as_object().at("error").is_object()) return safe_error(request.id,status);
        const auto& error = parsed.as_object().at("error").as_object();
        fields(error,{"code","message"});
        const auto code=text(error.at("code"),64);
        const auto message=world ? alliance::world_protocol::public_error(code) : alliance::progression_protocol::public_error(code);
        if(message.empty()) return safe_error(request.id,status);
        return json::object{{"v",4},{"id",request.id},{"ok",false},{"status",status},{"data",json::object{{"code",code},{"message",message}}}};
    }
    if(status != expected) return directory_operation(request.operation)
        ? directory_error(request, status, body) : safe_error(request.id, status);
    const auto value = parse_json(body);
    if(!value.is_object()) invalid();
    const auto& root = value.as_object();
    json::object data;
    if(world) {
        alliance::world_protocol::response(root); data=root;
    } else if(flex) {
        alliance::flexible_protocol::response(request.operation,root); data=root;
    } else if(unified) {
        alliance::unified_protocol::response(request.operation,root);
        if(request.operation=="battle_select_hero") {fields(root,{"battle"});data["battle"]=public_battle(root.at("battle"),true);}
        else data=root;
    } else if(progression) {
        alliance::progression_protocol::response(request.operation,root);
        data = root;
    } else if(directory_operation(request.operation)) {
        data = directory_data(request, root);
    } else if(request.operation == "logout") {
        if(text(root.at("status"), 32) != "logged_out") invalid();
        data["status"] = "logged_out";
    } else {
        data["account"] = public_account(root.at("account"));
        if(request.operation == "login") {
            const auto token = text(root.at("token"), 43);
            if(!ascii_word(token, 43, 43)) invalid();
            data["token"] = token;
        }
    }
    return json::object{{"v", 4}, {"id", request.id}, {"ok", true}, {"status", status}, {"data", std::move(data)}};
}
struct Settings {
    std::string secret, address;
    unsigned short port;
    std::string certificate, key;
};
std::string canonical_pem_newlines(const std::string& pem) {
    // The identity generator preserves OpenSSL's file bytes but writes LF in
    // the public profile. Native Windows OpenSSL can write CRLF in the file.
    // Compare those representations without changing either original file.
    std::string result;
    result.reserve(pem.size());
    for(std::size_t i = 0; i < pem.size(); ++i) {
        if(pem[i] == '\r' && i + 1 < pem.size() && pem[i + 1] == '\n') continue;
        result += pem[i];
    }
    return result;
}
Settings settings(const std::filesystem::path& runtime, const std::filesystem::path& identity,
                  const char*& phase) {
    phase = "runtime-config";
    const auto configuration = parse_json(regular_file(runtime / "config.json", max_json));
    if(!configuration.is_object()) invalid();
    const auto& root = configuration.as_object();
    if(root.at("format") != 1 || text(root.at("purpose"), 64) != "wesnoth-alliance-local" || !root.at("service").is_object()) invalid();
    const auto& service = root.at("service").as_object();
    if(text(service.at("host"), 16) != "127.0.0.1" || service.at("port") != 18765) invalid();
    Settings result;
    result.secret = text(service.at("bridge_secret"), 128);
    if(!ascii_word(result.secret, 43, 128)) invalid();
    phase = "public-profile";
    const auto profile_value = parse_json(regular_file(identity / "public-profile.json", max_json));
    if(!profile_value.is_object()) invalid();
    const auto& profile = profile_value.as_object();
    fields(profile, {"format", "protocol", "server_address", "port", "minimum_tls", "certificate_pem", "certificate_sha256"});
    if(profile.at("format") != 1 || text(profile.at("protocol"), 64) != "wesnoth-alliance-tls" ||
       text(profile.at("minimum_tls"), 8) != "1.2") invalid();
    result.address = text(profile.at("server_address"), 64);
    Error error;
    const auto address = asio::ip::make_address(result.address, error);
    if(error || address.to_string() != result.address || address.is_unspecified() || address.is_multicast() ||
       result.address == "255.255.255.255" || result.address.find('%') != std::string::npos) invalid();
    if(!profile.at("port").is_int64() || profile.at("port").as_int64() != 15001) invalid();
    result.port = 15001;
    phase = "certificate-file";
    result.certificate = regular_file(identity / "server-cert.pem", 16384);
    phase = "certificate-profile";
    if(canonical_pem_newlines(result.certificate) != text(profile.at("certificate_pem"), 16384)) invalid();
    phase = "certificate-validation";
    auto bio = std::unique_ptr<BIO, decltype(&BIO_free)>(BIO_new_mem_buf(result.certificate.data(), result.certificate.size()), BIO_free);
    auto cert = std::unique_ptr<X509, decltype(&X509_free)>(PEM_read_bio_X509(bio.get(), nullptr, nullptr, nullptr), X509_free);
    if(!cert || X509_check_ip_asc(cert.get(), result.address.c_str(), 0) != 1 ||
       X509_cmp_current_time(X509_get0_notBefore(cert.get())) >= 0 ||
       X509_cmp_current_time(X509_get0_notAfter(cert.get())) <= 0) invalid();
    unsigned char digest[EVP_MAX_MD_SIZE]; unsigned count = 0;
    if(!X509_digest(cert.get(), EVP_sha256(), digest, &count) || count != SHA256_DIGEST_LENGTH) invalid();
    std::string fingerprint;
    for(unsigned i = 0; i < count; ++i) {
        fingerprint += "0123456789abcdef"[digest[i] >> 4];
        fingerprint += "0123456789abcdef"[digest[i] & 15];
    }
    if(fingerprint != text(profile.at("certificate_sha256"), 64)) invalid();
    phase = "private-key-file";
    result.key = regular_file(identity / "server-key.pem", 16384);
    return result;
}

void check_backend(const std::string& secret) {
    asio::io_context io;
    tcp::socket socket(io);
    asio::steady_timer timer(io);
    bool passed = false;
    http::request<http::empty_body> request(http::verb::get, "/internal/v1/health", 11);
    request.set(http::field::host, "127.0.0.1:18765");
    request.set(http::field::authorization, "Bearer " + secret);
    request.set(http::field::connection, "close");
    http::response_parser<http::string_body> response;
    response.body_limit(max_json); response.header_limit(8192);
    boost::beast::flat_buffer buffer(8192);
    const auto finish = [&] {
        Error ignored; timer.cancel(); socket.cancel(ignored); socket.close(ignored);
    };
    timer.expires_after(std::chrono::seconds(6));
    timer.async_wait([&](Error error) { if(!error) finish(); });
    socket.async_connect({asio::ip::make_address_v4("127.0.0.1"), 18765}, [&](Error error) {
        if(error) { finish(); return; }
        http::async_write(socket, request, [&](Error error, std::size_t) {
            if(error) { finish(); return; }
            http::async_read(socket, buffer, response, [&](Error error, std::size_t) {
                if(!error) {
                    try {
                        if(response.get().result_int() != 200 ||
                           response.get()[http::field::content_type].find("application/json") != 0) invalid();
                        const auto value = parse_json(response.get().body());
                        const auto& data = value.as_object();
                        if(text(data.at("status"), 16) != "ok" ||
                           text(data.at("service"), 32) != "alliance" || data.at("api_version") != 1 || data.at("product_schema_version") != 4 ||
                           data.at("implementation_release") != 1192624) invalid();
                        passed = true;
                    } catch(...) {}
                }
                finish();
            });
        });
    });
    io.run();
    if(!passed) throw std::runtime_error("Local account service unavailable.");
}

class Session : public std::enable_shared_from_this<Session> {
    ssl::stream<tcp::socket> client_;
    tcp::socket backend_;
    asio::steady_timer deadline_;
    asio::steady_timer backend_deadline_;
    const std::string& secret_;
    std::shared_ptr<unsigned> active_;
    bool closed_ = false;
    bool responding_ = false;
    std::array<unsigned char, 4> header_{};
    std::vector<unsigned char> incoming_, outgoing_;
    Request request_;
    http::request<http::string_body> backend_request_;
    http::response_parser<http::string_body> backend_response_;
    boost::beast::flat_buffer backend_buffer_{8192};
    void close() {
        if(closed_) return;
        closed_ = true;
        Error ignored;
        deadline_.cancel();
        backend_deadline_.cancel();
        backend_.cancel(ignored); backend_.close(ignored);
        client_.next_layer().cancel(ignored); client_.next_layer().close(ignored);
    }
    void send(json::value value) {
        if(closed_ || responding_) return;
        responding_ = true;
        backend_deadline_.cancel();
        Error ignored; backend_.cancel(ignored); backend_.close(ignored);
        try { outgoing_ = compress_frame(value); } catch(...) { close(); return; }
        asio::async_write(client_, asio::buffer(outgoing_), [self = shared_from_this()](Error error, std::size_t) {
            if(error || self->closed_) { self->close(); return; }
            // No second request or replay is accepted on this connection.
            self->client_.async_shutdown([self](Error) { self->close(); });
        });
    }
    void backend_failed() { send(safe_error(request_.id, 503)); }
    void forward() {
        try {
            if(inflate_frame(incoming_) == "[alliance_health]\n[/alliance_health]\n") {
                responding_ = true;
                outgoing_ = compress_text_frame("[alliance_health]\nservice=\"alliance-accounts\"\napi=\"4\"\nimplementation_release=\"1192624\"\n[/alliance_health]\n");
                asio::async_write(client_, asio::buffer(outgoing_), [self=shared_from_this()](Error error, std::size_t) {
                    if(error) { self->close(); return; }
                    self->client_.async_shutdown([self](Error) { self->close(); });
                });
                return;
            }
            request_ = account_request(incoming_);
            if(request_.protocol < 4) {
                std::cout << "ALLIANCE ACCOUNT CLIENT UPDATE REQUIRED protocol=" << request_.protocol << " required_protocol=4 implementation_release=1192624" << std::endl;
                send(json::object{{"v",request_.protocol},{"id",request_.id},{"ok",false},{"status",426},
                    {"data",json::object{{"code","protocol"},{"message","Update the game to release 1192624 before connecting to this server."}}}});
                return;
            }
            backend_request_.method(request_.method);
            backend_request_.target(request_.target);
            backend_request_.version(11);
            backend_request_.set(http::field::host, "127.0.0.1:18765");
            backend_request_.set(http::field::authorization, "Bearer " + secret_);
            backend_request_.set(http::field::accept, "application/json");
            backend_request_.set(http::field::connection, "close");
            if(!request_.token.empty()) backend_request_.set("X-Player-Token", request_.token);
            if(request_.method == http::verb::post) {
                backend_request_.set(http::field::content_type, "application/json");
                backend_request_.body() = request_.body;
                backend_request_.prepare_payload();
            }
        } catch(...) { close(); return; }
        backend_deadline_.expires_after(std::chrono::seconds(6));
        backend_deadline_.async_wait([self = shared_from_this()](Error error) { if(!error) self->backend_failed(); });
        backend_.async_connect({asio::ip::make_address_v4("127.0.0.1"), 18765}, [self = shared_from_this()](Error error) {
            if(error) { self->backend_failed(); return; }
            http::async_write(self->backend_, self->backend_request_, [self](Error error, std::size_t) {
                if(error) { self->backend_failed(); return; }
                http::async_read(self->backend_, self->backend_buffer_, self->backend_response_, [self](Error error, std::size_t) {
                    if(error) { self->backend_failed(); return; }
                    const auto& response = self->backend_response_.get();
                    try {
                        if(response[http::field::content_type].find("application/json") != 0) invalid();
                        self->send(account_response(self->request_, response.result_int(), response.body()));
                    } catch(...) { self->backend_failed(); }
                });
            });
        });
    }
    void frame() {
        asio::async_read(client_, asio::buffer(header_), [self = shared_from_this()](Error error, std::size_t) {
            if(error) { self->close(); return; }
            std::size_t size = 0;
            for(auto byte : self->header_) size = (size << 8) | byte;
            if(size == 0 || size > max_frame) { self->close(); return; }
            self->incoming_.resize(size);
            asio::async_read(self->client_, asio::buffer(self->incoming_), [self](Error error, std::size_t) {
                if(error) { self->close(); return; }
                self->forward();
            });
        });
    }
public:
    Session(tcp::socket socket, ssl::context& context, const std::string& secret, std::shared_ptr<unsigned> active)
        : client_(std::move(socket), context), backend_(client_.get_executor()),
          deadline_(client_.get_executor()), backend_deadline_(client_.get_executor()), secret_(secret), active_(std::move(active)) {
        ++*active_;
        backend_response_.body_limit(max_json);
        backend_response_.header_limit(8192);
    }
    ~Session() { --*active_; }
    void start() {
        deadline_.expires_after(request_timeout);
        deadline_.async_wait([self = shared_from_this()](Error error) { if(!error) self->close(); });
        asio::async_read(client_.next_layer(), asio::buffer(header_), [self = shared_from_this()](Error error, std::size_t) {
            if(error || self->header_ != std::array<unsigned char, 4>{0, 0, 0, 1}) { self->close(); return; }
            self->header_.fill(0);
            asio::async_write(self->client_.next_layer(), asio::buffer(self->header_), [self](Error error, std::size_t) {
                if(error) { self->close(); return; }
                self->client_.async_handshake(ssl::stream_base::server, [self](Error error) {
                    if(error) { self->close(); return; }
                    self->frame();
                });
            });
        });
    }
};
class Listener {
    tcp::acceptor acceptor_;
    ssl::context& context_;
    const std::string& secret_;
    std::shared_ptr<unsigned> active_ = std::make_shared<unsigned>(0);
public:
    Listener(asio::io_context& io, ssl::context& context, const Settings& config)
        : acceptor_(io), context_(context), secret_(config.secret) {
        const tcp::endpoint endpoint(asio::ip::make_address(config.address), config.port);
        acceptor_.open(endpoint.protocol());
        // Do not enable address reuse: a second process must fail closed.
        acceptor_.bind(endpoint);
        acceptor_.listen(32);
    }
    void accept() {
        acceptor_.async_accept([this](Error error, tcp::socket socket) {
            if(!error && *active_ < max_connections)
                std::make_shared<Session>(std::move(socket), context_, secret_, active_)->start();
            // An unadmitted socket is closed by its destructor, without work.
            if(acceptor_.is_open()) accept();
        });
    }
};
} // namespace

int main(int argc, char** argv) {
    const char* phase = "arguments";
    try {
        if(argc == 2 && std::string(argv[1]) == "--version") {
            std::cout << "WESNOTH_ALLIANCE_ACCOUNT_BRIDGE protocol=4 max_connections=32 timeout_seconds=10\n";
            return 0;
        }
        std::map<std::string, std::string> args;
        for(int i = 1; i < argc; ++i) {
            const std::string key = argv[i];
            if((key != "--runtime" && key != "--identity") || ++i == argc || !args.emplace(key, argv[i]).second) invalid();
        }
        if(args.size() != 2) invalid();
        const auto config = settings(std::filesystem::absolute(args.at("--runtime")), std::filesystem::absolute(args.at("--identity")), phase);
        phase = "tls-context";
        asio::io_context io;
        ssl::context context(ssl::context::tls_server);
        context.set_options(ssl::context::no_compression);
        if(SSL_CTX_set_min_proto_version(context.native_handle(), TLS1_2_VERSION) != 1) invalid();
        context.use_certificate_chain(asio::buffer(config.certificate));
        context.use_private_key(asio::buffer(config.key), ssl::context::pem);
        if(SSL_CTX_check_private_key(context.native_handle()) != 1) invalid();
        phase = "backend-health";
        check_backend(config.secret);
        phase = "listener-bind";
        Listener listener(io, context, config);
        phase = "listener-start";
        listener.accept();
        asio::signal_set signals(io, SIGINT, SIGTERM);
        signals.async_wait([&io](Error, int) { io.stop(); });
        std::cout << "ALLIANCE ACCOUNT BRIDGE READY " << config.address << ':' << config.port
                  << " -> local account service\nKeep this window open. Ctrl+C stops the bridge.\n" << std::flush;
        phase = "serving";
        io.run();
        std::cout << "Alliance account bridge stopped.\n";
        return 0;
    } catch(const boost::system::system_error& error) {
        // A fixed phase and numeric OS/library code are safe; what() may
        // contain private input or library diagnostics and is never printed.
        std::cerr << "ERROR: Alliance account bridge failed; stage=" << phase
                  << "; error_code=" << error.code().value()
                  << ". Existing files were preserved.\n";
        return 1;
    } catch(...) {
        // Driver/JSON/SSL exceptions can embed private configuration or bytes.
        std::cerr << "ERROR: Alliance account bridge failed; stage=" << phase
                  << ". Check this startup stage. Existing files were preserved.\n";
        return 1;
    }
}
