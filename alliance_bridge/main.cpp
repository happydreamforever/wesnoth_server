// SPDX-License-Identifier: GPL-2.0-or-later
// Separate account listener. It never reads the guest game socket or submits
// game results. All application operations have a fixed loopback destination.
#include <boost/asio.hpp>
#include <boost/asio/ssl.hpp>
#include <boost/beast/http.hpp>
#include <boost/beast/core/flat_buffer.hpp>
#include <boost/json/src.hpp>
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
constexpr std::size_t max_frame = 65536, max_json = 32768;
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
    json::parse_options options; options.max_depth = 8;
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
std::vector<unsigned char> compress_frame(const json::value& value) {
    const auto input = json::serialize(value);
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
const std::set<std::string> starters{"spearman", "elvish-fighter", "orcish-grunt", "dwarvish-fighter", "drake-fighter", "skeleton"};
std::size_t utf8_characters(const std::string& value) {
    std::size_t result = 0;
    for(unsigned char c : value) if((c & 0xc0) != 0x80) ++result;
    return result;
}
struct Request {
    std::string id, operation, token, body;
    http::verb method = http::verb::post;
};
Request account_request(const std::vector<unsigned char>& bytes) {
    auto value = parse_json(inflate_frame(bytes));
    if(!value.is_object()) invalid();
    const auto& root = value.as_object();
    fields(root, {"v", "id", "op", "body"}, {"token"});
    if(!root.at("v").is_int64() || root.at("v").as_int64() != 1) invalid();
    Request result;
    result.id = text(root.at("id"), 32); if(!request_id(result.id)) invalid();
    result.operation = text(root.at("op"), 16);
    if(!root.at("body").is_object()) invalid();
    const auto& body = root.at("body").as_object();
    if(result.operation == "register" || result.operation == "login") {
        if(root.contains("token")) invalid();
        if(result.operation == "register") fields(body, {"username", "password", "starter_id"});
        else fields(body, {"username", "password"});
        const auto username = text(body.at("username"), 24);
        if(!ascii_word(username, 3, 24) || username.find('-') != std::string::npos) invalid();
        const auto password = text(body.at("password"), 512);
        const auto length = utf8_characters(password);
        if(length < (result.operation == "register" ? 12U : 1U) || length > 128 || password.find('\0') != std::string::npos) invalid();
        if(result.operation == "register" && !starters.count(text(body.at("starter_id"), 40))) invalid();
    } else if(result.operation == "me" || result.operation == "logout") {
        fields(body, {});
        if(!root.contains("token")) invalid();
        result.token = text(root.at("token"), 43);
        if(!ascii_word(result.token, 43, 43)) invalid();
        if(result.operation == "me") result.method = http::verb::get;
    } else invalid();
    result.body = json::serialize(body);
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
    return {{"v", 1}, {"id", id}, {"ok", false}, {"status", status},
            {"data", {{"code", code}, {"message", message}}}};
}
json::object public_account(const json::value& value) {
    if(!value.is_object()) invalid();
    const auto& source = value.as_object();
    const auto id = text(source.at("_id"), 64), username = text(source.at("username"), 24);
    if(!ascii_word(username, 3, 24) || !ascii_word(id, 1, 64) || !source.at("leader").is_object()) invalid();
    const auto& leader = source.at("leader").as_object();
    json::object result_leader;
    for(const auto* name : {"starter_id", "unit_type"}) {
        const auto item = text(leader.at(name), 64);
        if(item.empty()) invalid();
        result_leader[name] = item;
    }
    if(!starters.count(text(leader.at("starter_id"), 40))) invalid();
    for(const auto* name : {"level", "experience", "total_experience"}) {
        const auto& item = leader.at(name);
        if(!item.is_int64() || item.as_int64() < 0 || item.as_int64() > 2147483647) invalid();
        if(std::string(name) == "level" && (item.as_int64() < 1 || item.as_int64() > 3)) invalid();
        result_leader[name] = item;
    }
    return {{"id", id}, {"username", username}, {"leader", std::move(result_leader)}};
}
json::value account_response(const Request& request, unsigned status, const std::string& body) {
    const unsigned expected = request.operation == "register" ? 201 : 200;
    if(status != expected) return safe_error(request.id, status);
    const auto value = parse_json(body);
    if(!value.is_object()) invalid();
    const auto& root = value.as_object();
    json::object data;
    if(request.operation == "logout") {
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
    return json::object{{"v", 1}, {"id", request.id}, {"ok", true}, {"status", status}, {"data", std::move(data)}};
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
                           text(data.at("service"), 32) != "alliance" || data.at("api_version") != 1) invalid();
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
            request_ = account_request(incoming_);
            backend_request_.method(request_.method);
            backend_request_.target("/internal/v1/" + request_.operation);
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
            std::cout << "WESNOTH_ALLIANCE_ACCOUNT_BRIDGE protocol=1 max_connections=32 timeout_seconds=10\n";
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
