#pragma once
/**
 * redfish_sdk/event_listener.hpp
 *
 * RedfishEventListener — embedded HTTP server that receives push-mode
 * event notifications from a BMC EventService subscription.
 *
 * Design ref: RSDK-DESIGN-002 §15
 * FR5.3 features: context validation, latency logging, per-IP counter,
 *                 ring-buffer, buffered GET endpoint.
 *
 * Implementation: raw POSIX sockets + std::thread (no Boost dependency).
 */

#include "redfish_sdk/services/event_service.hpp"
#include <atomic>
#include <deque>
#include <functional>
#include <map>
#include <mutex>
#include <string>
#include <thread>
#include <vector>

namespace redfish {

class ClientContext;  // forward declaration — optional wiring

/**
 * Embedded HTTP server that receives BMC-pushed Redfish events.
 *
 * Usage:
 *   RedfishEventListener listener{9090, "0.0.0.0", "My-Context"};
 *   listener.on_event([](const RedfishEvent& e){ ... });
 *   listener.start();
 *   // ... receive events ...
 *   listener.stop();   // or just let destructor do it
 */
class RedfishEventListener {
public:
    /**
     * Construct a listener.
     *
     * @param port             TCP port to bind.
     * @param host             Interface address (default all interfaces).
     * @param expected_context When non-empty, only events whose JSON
     *                         "Context" field matches are dispatched (FR5.3).
     * @param buffer_size      Capacity of the in-memory event ring buffer
     *                         (FR5.3). Oldest entries are evicted when full.
     */
    explicit RedfishEventListener(
        uint16_t         port,
        std::string_view host             = "0.0.0.0",
        std::string_view expected_context = "",
        uint32_t         buffer_size      = 200
    );

    /**
     * Destructor — calls stop() if the server is running. Blocks until
     * the supervisor thread has exited.
     */
    ~RedfishEventListener();

    // Move-only (socket + thread are not copyable)
    RedfishEventListener(RedfishEventListener&&) noexcept;
    RedfishEventListener& operator=(RedfishEventListener&&) noexcept;
    RedfishEventListener(const RedfishEventListener&)            = delete;
    RedfishEventListener& operator=(const RedfishEventListener&) = delete;

    /**
     * Wire a ClientContext for MessageRegistry decoding. Optional — the
     * listener works without it; MessageId fields will be left unresolved.
     */
    void use_context(ClientContext& ctx);

    // ------------------------------------------------------------------
    // Callback registration
    // ------------------------------------------------------------------

    /** Register a callback invoked for every incoming event. */
    void on_event(std::function<void(const RedfishEvent&)> callback);

    /**
     * Register a callback invoked only when the event's EventType matches.
     * @param event_type  e.g. "Alert", "ResourceUpdated", "StatusChange"
     */
    void on_event_type(
        std::string_view                         event_type,
        std::function<void(const RedfishEvent&)> callback
    );

    /**
     * Register a callback invoked only when the MessageId registry prefix
     * matches (the part before the first '.').
     * @param registry_prefix  e.g. "Base", "OpenBMC", "TaskEvent"
     */
    void on_registry(
        std::string_view                         registry_prefix,
        std::function<void(const RedfishEvent&)> callback
    );

    // ------------------------------------------------------------------
    // Lifecycle
    // ------------------------------------------------------------------

    /**
     * Start the listener. Non-blocking — the server runs on a background
     * thread. Returns only after the socket is bound and listening.
     *
     * @throws RedfishSDKError if the socket cannot be bound.
     */
    void start();

    /** Stop the listener. Blocks until the supervisor thread has exited. */
    void stop();

    /** True if start() has been called and stop() has not yet returned. */
    bool is_running() const;

    /** Returns the base URL the listener is reachable at. */
    std::string listen_url() const;

    // ------------------------------------------------------------------
    // FR5.3 — introspection
    // ------------------------------------------------------------------

    /**
     * Return a snapshot of buffered events (most-recently-received first
     * is NOT guaranteed — order is chronological, oldest-first).
     * Thread-safe.
     */
    std::vector<RedfishEvent> get_buffered_events() const;

    /**
     * Return a copy of per-source-IP event counts.
     * Thread-safe.
     */
    std::map<std::string, uint32_t> get_ip_stats() const;

private:
    // Configuration
    uint16_t    port_;
    std::string host_;
    std::string expected_context_;
    uint32_t    buffer_size_;

    // Optional context link
    ClientContext* ctx_ptr_ = nullptr;

    // Callbacks
    std::vector<std::function<void(const RedfishEvent&)>>                global_cbs_;
    std::map<std::string, std::vector<std::function<void(const RedfishEvent&)>>> type_cbs_;
    std::map<std::string, std::vector<std::function<void(const RedfishEvent&)>>> registry_cbs_;

    // State
    std::atomic<bool> running_{false};
    int               server_fd_  = -1;
    int               wake_read_  = -1;   // self-pipe read end
    int               wake_write_ = -1;   // self-pipe write end
    std::thread       supervisor_;

    // FR5.3 runtime data (guarded by stats_mutex_)
    mutable std::mutex               stats_mutex_;
    std::deque<RedfishEvent>         event_buffer_;
    std::map<std::string, uint32_t>  ip_stats_;

    // Internal methods
    void   _supervisor_loop();
    void   _handle_connection(int client_fd, const std::string& peer_ip);
    void   _dispatch(const RedfishEvent& event);
    void   _record_event(const RedfishEvent& event, const std::string& ip);
    static std::string _read_http_body(int fd);
    static void        _send_204(int fd);
    static void        _send_json_200(int fd, const std::string& json_body);
    static std::string _parse_registry_prefix(const std::string& message_id);
};

} // namespace redfish
