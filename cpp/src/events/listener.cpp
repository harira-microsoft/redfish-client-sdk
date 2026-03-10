// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

/**
 * src/events/listener.cpp
 *
 * RedfishEventListener — embedded HTTP server for push-mode Redfish events.
 *
 * Design ref:  RSDK-DESIGN-002 §15
 * FR5.3:       context validation, latency logging, per-IP counter,
 *              ring-buffer, buffered GET endpoint.
 *
 * Transport:   raw POSIX TCP sockets + std::thread
 *              (no Boost, no asio dependency).
 *
 * HTTP:        minimal HTTP/1.1 parser — reads headers, then Content-Length
 *              bytes for the body.  Only POST and GET on the /events path
 *              are handled; all other requests receive 405.
 */

#include "redfish_sdk/event_listener.hpp"
#include "redfish_sdk/errors.hpp"

// POSIX headers
#include <arpa/inet.h>
#include <fcntl.h>
#include <netinet/in.h>
#include <sys/socket.h>
#include <unistd.h>

#include <algorithm>
#include <cassert>
#include <chrono>
#include <cstring>
#include <iomanip>
#include <iostream>
#include <sstream>
#include <stdexcept>
#include <string>
#include <utility>

#include <nlohmann/json.hpp>

// Simple SDK debug logger — mirrors the pattern used elsewhere in the SDK.
// Production builds strip DEBUG calls via -DREDFISH_LOG_LEVEL=WARN.
static void _log_debug(const std::string& msg)
{
    const char* lvl = std::getenv("REDFISH_LOG_LEVEL");
    if (lvl && (std::string(lvl) == "DEBUG" || std::string(lvl) == "TRACE")) {
        std::cerr << "[REDFISH DEBUG] " << msg << "\n";
    }
}
static void _log_warn(const std::string& msg)
{
    std::cerr << "[REDFISH WARN ] " << msg << "\n";
}

namespace redfish {

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

static std::string addr_to_string(const sockaddr_in& addr)
{
    char buf[INET_ADDRSTRLEN] = {};
    ::inet_ntop(AF_INET, &addr.sin_addr, buf, sizeof(buf));
    return buf;
}

/** Parse ISO 8601 timestamp "YYYY-MM-DDTHH:MM:SSZ" to a time_point. */
static bool parse_iso8601(const std::string& ts,
                           std::chrono::system_clock::time_point& out)
{
    // We accept "YYYY-MM-DDTHH:MM:SSZ" only (no fractional seconds).
    // Silently fail on other formats — callers treat false as "skip latency".
    std::tm t{};
    std::istringstream ss(ts);
    ss >> std::get_time(&t, "%Y-%m-%dT%H:%M:%S");
    if (ss.fail()) return false;
    std::time_t tt = ::timegm(&t);
    if (tt == -1) return false;
    out = std::chrono::system_clock::from_time_t(tt);
    return true;
}

// ---------------------------------------------------------------------------
// Constructor / destructor
// ---------------------------------------------------------------------------

RedfishEventListener::RedfishEventListener(
    uint16_t         port,
    std::string_view host,
    std::string_view expected_context,
    uint32_t         buffer_size
)
    : port_(port)
    , host_(host)
    , expected_context_(expected_context)
    , buffer_size_(buffer_size)
{}

RedfishEventListener::~RedfishEventListener()
{
    stop();
}

RedfishEventListener::RedfishEventListener(RedfishEventListener&& o) noexcept
    : port_(o.port_)
    , host_(std::move(o.host_))
    , expected_context_(std::move(o.expected_context_))
    , buffer_size_(o.buffer_size_)
    , ctx_ptr_(o.ctx_ptr_)
    , global_cbs_(std::move(o.global_cbs_))
    , type_cbs_(std::move(o.type_cbs_))
    , registry_cbs_(std::move(o.registry_cbs_))
    , running_(o.running_.load())
    , server_fd_(o.server_fd_)
    , wake_read_(o.wake_read_)
    , wake_write_(o.wake_write_)
    , supervisor_(std::move(o.supervisor_))
    , event_buffer_(std::move(o.event_buffer_))
    , ip_stats_(std::move(o.ip_stats_))
{
    o.server_fd_  = -1;
    o.wake_read_  = -1;
    o.wake_write_ = -1;
    o.running_.store(false);
}

RedfishEventListener& RedfishEventListener::operator=(RedfishEventListener&& o) noexcept
{
    if (this != &o) {
        stop();
        port_             = o.port_;
        host_             = std::move(o.host_);
        expected_context_ = std::move(o.expected_context_);
        buffer_size_      = o.buffer_size_;
        ctx_ptr_          = o.ctx_ptr_;
        global_cbs_       = std::move(o.global_cbs_);
        type_cbs_         = std::move(o.type_cbs_);
        registry_cbs_     = std::move(o.registry_cbs_);
        running_.store(o.running_.load());
        server_fd_        = o.server_fd_;
        wake_read_        = o.wake_read_;
        wake_write_       = o.wake_write_;
        supervisor_       = std::move(o.supervisor_);
        event_buffer_     = std::move(o.event_buffer_);
        ip_stats_         = std::move(o.ip_stats_);
        o.server_fd_  = -1;
        o.wake_read_  = -1;
        o.wake_write_ = -1;
        o.running_.store(false);
    }
    return *this;
}

// ---------------------------------------------------------------------------
// Configuration
// ---------------------------------------------------------------------------

void RedfishEventListener::use_context(ClientContext& ctx)
{
    ctx_ptr_ = &ctx;
}

// ---------------------------------------------------------------------------
// Callback registration
// ---------------------------------------------------------------------------

void RedfishEventListener::on_event(std::function<void(const RedfishEvent&)> cb)
{
    global_cbs_.push_back(std::move(cb));
}

void RedfishEventListener::on_event_type(
    std::string_view                         event_type,
    std::function<void(const RedfishEvent&)> cb)
{
    type_cbs_[std::string(event_type)].push_back(std::move(cb));
}

void RedfishEventListener::on_registry(
    std::string_view                         registry_prefix,
    std::function<void(const RedfishEvent&)> cb)
{
    registry_cbs_[std::string(registry_prefix)].push_back(std::move(cb));
}

// ---------------------------------------------------------------------------
// Lifecycle
// ---------------------------------------------------------------------------

void RedfishEventListener::start()
{
    if (running_.load()) return;

    // Create self-pipe for clean shutdown signalling
    int pipe_fds[2];
    if (::pipe(pipe_fds) != 0)
        throw RedfishSDKError("RedfishEventListener: pipe() failed");
    wake_read_  = pipe_fds[0];
    wake_write_ = pipe_fds[1];

    // Create server socket
    server_fd_ = ::socket(AF_INET, SOCK_STREAM, 0);
    if (server_fd_ < 0) {
        ::close(wake_read_); ::close(wake_write_);
        throw RedfishSDKError("RedfishEventListener: socket() failed");
    }

    int opt = 1;
    ::setsockopt(server_fd_, SOL_SOCKET, SO_REUSEADDR, &opt, sizeof(opt));

    sockaddr_in addr{};
    addr.sin_family      = AF_INET;
    addr.sin_port        = htons(port_);
    addr.sin_addr.s_addr = INADDR_ANY;
    if (host_ != "0.0.0.0" && !host_.empty()) {
        ::inet_pton(AF_INET, host_.c_str(), &addr.sin_addr);
    }

    if (::bind(server_fd_, reinterpret_cast<sockaddr*>(&addr), sizeof(addr)) < 0) {
        ::close(server_fd_); ::close(wake_read_); ::close(wake_write_);
        throw RedfishSDKError("RedfishEventListener: bind() failed on port "
                              + std::to_string(port_));
    }
    ::listen(server_fd_, SOMAXCONN);

    running_.store(true);
    supervisor_ = std::thread([this]{ _supervisor_loop(); });

    _log_debug("RedfishEventListener started on " + listen_url());
}

void RedfishEventListener::stop()
{
    if (!running_.load()) return;
    running_.store(false);

    // Wake the select() in the supervisor via the self-pipe
    if (wake_write_ >= 0) {
        char byte = 1;
        (void)::write(wake_write_, &byte, 1);
    }

    if (supervisor_.joinable()) supervisor_.join();

    if (server_fd_ >= 0)  { ::close(server_fd_);  server_fd_  = -1; }
    if (wake_read_ >= 0)  { ::close(wake_read_);  wake_read_  = -1; }
    if (wake_write_ >= 0) { ::close(wake_write_); wake_write_ = -1; }

    _log_debug("RedfishEventListener stopped");
}

bool RedfishEventListener::is_running() const { return running_.load(); }

std::string RedfishEventListener::listen_url() const
{
    return "http://" + host_ + ":" + std::to_string(port_) + "/events";
}

// ---------------------------------------------------------------------------
// FR5.3 — introspection
// ---------------------------------------------------------------------------

std::vector<RedfishEvent> RedfishEventListener::get_buffered_events() const
{
    std::lock_guard<std::mutex> lk(stats_mutex_);
    return std::vector<RedfishEvent>(event_buffer_.begin(), event_buffer_.end());
}

std::map<std::string, uint32_t> RedfishEventListener::get_ip_stats() const
{
    std::lock_guard<std::mutex> lk(stats_mutex_);
    return ip_stats_;
}

// ---------------------------------------------------------------------------
// Supervisor thread — accept loop
// ---------------------------------------------------------------------------

void RedfishEventListener::_supervisor_loop()
{
    while (running_.load()) {
        fd_set rfds;
        FD_ZERO(&rfds);
        FD_SET(server_fd_, &rfds);
        FD_SET(wake_read_, &rfds);
        int nfds = std::max(server_fd_, wake_read_) + 1;

        // Wait with 1-second timeout so we notice stop() quickly even if
        // the self-pipe byte races with the stop flag check.
        struct timeval tv { 1, 0 };
        int ret = ::select(nfds, &rfds, nullptr, nullptr, &tv);
        if (ret < 0) break;  // interrupted or error

        // Self-pipe signalled — time to exit
        if (FD_ISSET(wake_read_, &rfds)) break;

        if (!FD_ISSET(server_fd_, &rfds)) continue;

        sockaddr_in peer_addr{};
        socklen_t   peer_len = sizeof(peer_addr);
        int client_fd = ::accept(server_fd_,
                                  reinterpret_cast<sockaddr*>(&peer_addr),
                                  &peer_len);
        if (client_fd < 0) continue;

        std::string peer_ip = addr_to_string(peer_addr);

        // Spawn per-connection thread (short-lived)
        std::thread conn_thread(
            [this, client_fd, peer_ip]() {
                _handle_connection(client_fd, peer_ip);
                ::close(client_fd);
            }
        );
        conn_thread.detach();
    }
}

// ---------------------------------------------------------------------------
// Per-connection handler
// ---------------------------------------------------------------------------

void RedfishEventListener::_handle_connection(int client_fd,
                                               const std::string& peer_ip)
{
    // --- Read request line + headers ---
    // Read until we see the blank line "\r\n\r\n".
    std::string header_buf;
    header_buf.reserve(2048);
    char ch = 0;
    while (true) {
        int n = static_cast<int>(::recv(client_fd, &ch, 1, 0));
        if (n <= 0) return;
        header_buf += ch;
        if (header_buf.size() >= 4 &&
            header_buf.compare(header_buf.size() - 4, 4, "\r\n\r\n") == 0)
            break;
        if (header_buf.size() > 16384) return;  // oversized header — drop
    }

    // Parse first line to determine method and path
    auto first_nl = header_buf.find("\r\n");
    if (first_nl == std::string::npos) return;
    std::string request_line = header_buf.substr(0, first_nl);

    std::string method, path;
    {
        std::istringstream rl(request_line);
        rl >> method >> path;
    }

    // Parse Content-Length from headers
    size_t content_length = 0;
    {
        std::string headers_part = header_buf.substr(first_nl + 2);
        std::istringstream hs(headers_part);
        std::string line;
        while (std::getline(hs, line)) {
            if (!line.empty() && line.back() == '\r') line.pop_back();
            std::string lower_line = line;
            std::transform(lower_line.begin(), lower_line.end(),
                            lower_line.begin(),
                            [](unsigned char c){ return static_cast<unsigned char>(std::tolower(c)); });
            if (lower_line.rfind("content-length:", 0) == 0) {
                content_length = static_cast<size_t>(
                    std::stoull(line.substr(line.find(':') + 1)));
            }
        }
    }

    // --- Handle GET (buffered events polling) ---
    if (method == "GET") {
        auto events = get_buffered_events();
        nlohmann::json arr = nlohmann::json::array();
        for (const auto& ev : events) {
            arr.push_back({
                {"EventType",          ev.event_type},
                {"EventTimestamp",     ev.event_timestamp},
                {"MessageId",          ev.message_id},
                {"Message",            ev.message},
                {"Severity",           ev.severity},
                {"OriginOfCondition",  ev.origin_of_condition.value_or("")},
            });
        }
        _send_json_200(client_fd, arr.dump());
        return;
    }

    // --- Handle POST ---
    if (method != "POST") {
        // 405 Method Not Allowed
        const char resp405[] = "HTTP/1.1 405 Method Not Allowed\r\n"
                               "Content-Length: 0\r\n\r\n";
        ::send(client_fd, resp405, sizeof(resp405) - 1, 0);
        return;
    }

    // Read body
    std::string body_str;
    if (content_length > 0) {
        body_str.resize(content_length);
        size_t read_so_far = 0;
        while (read_so_far < content_length) {
            int n = static_cast<int>(::recv(client_fd,
                                            &body_str[read_so_far],
                                            content_length - read_so_far, 0));
            if (n <= 0) break;
            read_so_far += static_cast<size_t>(n);
        }
    }

    // Record reception time for latency calculation (FR5.3)
    auto reception_tp = std::chrono::system_clock::now();

    // Parse JSON
    nlohmann::json payload;
    try {
        payload = nlohmann::json::parse(body_str);
    } catch (...) {
        _log_warn("Event listener: unparseable JSON payload from " + peer_ip);
        _send_204(client_fd);
        return;
    }

    // FR5.3 — context validation
    if (!expected_context_.empty()) {
        std::string ev_context;
        if (payload.is_object() && payload.contains("Context") &&
            payload["Context"].is_string()) {
            ev_context = payload["Context"].get<std::string>();
        }
        if (ev_context != expected_context_) {
            _log_debug("Context mismatch: expected=" + expected_context_ +
                       " got=" + ev_context + " peer=" + peer_ip);
            _send_204(client_fd);
            return;
        }
    }

    // Extract events array
    std::vector<nlohmann::json> records;
    if (payload.is_object() && payload.contains("Events") &&
        payload["Events"].is_array()) {
        for (const auto& rec : payload["Events"])
            records.push_back(rec);
    } else {
        records.push_back(payload);
    }

    for (const auto& rec : records) {
        if (!rec.is_object()) continue;

        RedfishEvent ev;
        if (rec.contains("EventId")        && rec["EventId"].is_string())
            ev.event_id = rec["EventId"].get<std::string>();
        if (rec.contains("EventType")      && rec["EventType"].is_string())
            ev.event_type = rec["EventType"].get<std::string>();
        if (rec.contains("EventTimestamp") && rec["EventTimestamp"].is_string())
            ev.event_timestamp = rec["EventTimestamp"].get<std::string>();
        if (rec.contains("MessageId")      && rec["MessageId"].is_string())
            ev.message_id = rec["MessageId"].get<std::string>();
        if (rec.contains("Message")        && rec["Message"].is_string())
            ev.message = rec["Message"].get<std::string>();
        if (rec.contains("Severity")       && rec["Severity"].is_string())
            ev.severity = rec["Severity"].get<std::string>();
        else if (rec.contains("MessageSeverity") && rec["MessageSeverity"].is_string())
            ev.severity = rec["MessageSeverity"].get<std::string>();
        if (rec.contains("OriginOfCondition") &&
            rec["OriginOfCondition"].is_object() &&
            rec["OriginOfCondition"].contains("@odata.id"))
            ev.origin_of_condition =
                rec["OriginOfCondition"]["@odata.id"].get<std::string>();
        ev.raw = rec;

        // FR5.3 — latency logging
        if (!ev.event_timestamp.empty()) {
            std::chrono::system_clock::time_point event_tp;
            if (parse_iso8601(ev.event_timestamp, event_tp)) {
                auto delta = std::chrono::duration_cast<std::chrono::milliseconds>(
                    reception_tp - event_tp).count();
                _log_debug("Event latency: " + std::to_string(delta) + " ms"
                           "  EventTimestamp=" + ev.event_timestamp +
                           "  MessageId=" + ev.message_id);
            }
        }

        // FR5.3 — record + buffer
        _record_event(ev, peer_ip);

        // Dispatch callbacks
        _dispatch(ev);
    }

    _send_204(client_fd);
}

// ---------------------------------------------------------------------------
// Dispatch callbacks
// ---------------------------------------------------------------------------

void RedfishEventListener::_dispatch(const RedfishEvent& event)
{
    // 1. Global callbacks
    for (const auto& cb : global_cbs_) cb(event);

    // 2. EventType-filtered callbacks
    if (!event.event_type.empty()) {
        auto it = type_cbs_.find(event.event_type);
        if (it != type_cbs_.end())
            for (const auto& cb : it->second) cb(event);
    }

    // 3. Registry-prefix callbacks
    if (!event.message_id.empty()) {
        std::string prefix = _parse_registry_prefix(event.message_id);
        auto it = registry_cbs_.find(prefix);
        if (it != registry_cbs_.end())
            for (const auto& cb : it->second) cb(event);
    }
}

// ---------------------------------------------------------------------------
// FR5.3 — record event: per-IP counter + ring buffer
// ---------------------------------------------------------------------------

void RedfishEventListener::_record_event(const RedfishEvent& event,
                                          const std::string&   ip)
{
    std::lock_guard<std::mutex> lk(stats_mutex_);
    ip_stats_[ip]++;
    event_buffer_.push_back(event);
    while (event_buffer_.size() > buffer_size_)
        event_buffer_.pop_front();
}

// ---------------------------------------------------------------------------
// Static helpers
// ---------------------------------------------------------------------------

std::string RedfishEventListener::_parse_registry_prefix(
    const std::string& message_id)
{
    auto dot = message_id.find('.');
    return (dot == std::string::npos) ? message_id : message_id.substr(0, dot);
}

void RedfishEventListener::_send_204(int fd)
{
    const char resp[] = "HTTP/1.1 204 No Content\r\nContent-Length: 0\r\n\r\n";
    ::send(fd, resp, sizeof(resp) - 1, 0);
}

void RedfishEventListener::_send_json_200(int fd, const std::string& json_body)
{
    std::string resp =
        "HTTP/1.1 200 OK\r\n"
        "Content-Type: application/json\r\n"
        "Content-Length: " + std::to_string(json_body.size()) + "\r\n"
        "\r\n" + json_body;
    ::send(fd, resp.c_str(), resp.size(), 0);
}

} // namespace redfish
