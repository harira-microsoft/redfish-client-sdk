// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

#pragma once
/**
 * redfish_sdk/services/ras_service.hpp
 *
 * RAS API service handle — endpoint discovery, CPER event subscription,
 * large-CPER retrieval via AdditionalDataUri, and CPAD submission.
 *
 * Terminology:
 *   CPER  — Common Platform Error Record (UEFI 2.9A)
 *   CPAD  — Common Platform Action Descriptor (OCP RAS API v1.0)
 *   CreatorID   — GUID identifying the vendor analyzer for a CPER stream.
 *   PartitionID — BMC-assigned routing ID used to direct CPADs to the
 *                 correct silicon endpoint.
 */

#include "redfish_sdk/models/redfish_types.hpp"
#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/protocol/response.hpp"

#include <cstdint>
#include <map>
#include <optional>
#include <string>
#include <vector>

#include <nlohmann/json.hpp>

namespace redfish {

// ---------------------------------------------------------------------------
// CPER severity / queue types
// ---------------------------------------------------------------------------

/**
 * Maps to the five RAS API CPER queues defined in the OCP RAS API v1.0 spec.
 */
enum class CperSeverity {
    PlatformEvent,   ///< Informational / Platform Action Events (not errors)
    Informational,   ///< Deferred errors including poison generation
    Corrected,       ///< Hardware-corrected errors
    Recoverable,     ///< OS-survivable errors (poison consumption, PCIe)
    Fatal,           ///< OS-crashing errors / hardware crashdumps
    Unknown,
};

/// Infer CperSeverity from a Redfish MessageId string (case-insensitive).
CperSeverity cper_severity_from_message_id(const std::string& message_id);

// ---------------------------------------------------------------------------
// Data models
// ---------------------------------------------------------------------------

/**
 * A silicon RAS API endpoint discovered by the BMC and exposed via Redfish.
 */
struct RasEndpoint {
    std::string              endpoint_id;
    std::string              creator_id;       ///< GUID — vendor analyzer ID
    std::string              fru_id;           ///< GUID — unique FRU instance
    std::string              partition_id;     ///< BMC-assigned routing ID
    std::vector<std::string> supported_queues;
    std::string              uri;
    nlohmann::json           raw;
};

/**
 * A CPER-carrying Redfish event delivered by the BMC.
 *
 * Small CPERs are embedded inline in ``cper_data``.  Large CPERs set
 * ``additional_data_uri``; use RasServiceHandle::fetch_cper_data() to
 * retrieve the binary payload.
 */
struct CperEvent {
    std::string                          event_id;
    std::string                          message_id;
    CperSeverity                         severity = CperSeverity::Unknown;
    std::string                          timestamp;
    std::optional<std::string>           origin_of_condition;
    std::optional<std::vector<uint8_t>>  cper_data;           ///< inline CPER bytes
    std::optional<std::string>           additional_data_uri;
    nlohmann::json                       raw;

    /// Parse a single EventRecord object from a Redfish EventMessage payload.
    static CperEvent from_event_record(const nlohmann::json& record);
};

/**
 * A Common Platform Action Descriptor (CPAD) to submit to the BMC.
 *
 * The BMC uses ``partition_id`` to route the action to the correct silicon
 * endpoint.  ``payload`` is the raw binary CPAD blob; it is transmitted
 * base64-encoded in the JSON body.
 */
struct CpadRecord {
    std::string          platform_id;   ///< identifies this BMC in the fleet
    std::string          partition_id;  ///< identifies the target silicon endpoint
    std::string          creator_id;    ///< identifies the issuing analyzer
    std::vector<uint8_t> payload;       ///< binary CPAD blob
    std::string          fru_id;
    std::string          fru_text;      ///< physical location label
};

// ---------------------------------------------------------------------------
// Service handle
// ---------------------------------------------------------------------------

class RasServiceHandle {
public:
    RasServiceHandle(
        IHttpClient&                              http,
        const AuthState&                          auth_state,
        const std::map<std::string, std::string>& discovery_map
    );

    // ── Endpoint discovery ────────────────────────────────────────────────

    /// Discover all RAS API endpoints exposed by the BMC.
    std::vector<RasEndpoint> discover_endpoints();

    // ── CPER event subscription ───────────────────────────────────────────

    /**
     * Subscribe to CPER-carrying Redfish events from this BMC.
     *
     * ``registry_prefixes`` and ``message_ids`` narrow the subscription.
     * Leave both empty to receive all events (filter client-side with
     * parse_cper_events).
     */
    RedfishResponse subscribe_cper_events(
        const std::string&              destination,
        const std::vector<std::string>& registry_prefixes = {},
        const std::vector<std::string>& message_ids       = {},
        const std::string&              context           = "RAS-CPER",
        const std::string&              event_format_type = "Event"
    );

    // ── Large-CPER retrieval ──────────────────────────────────────────────

    /// Fetch a CPER payload from the BMC via the AdditionalDataUri in an event.
    std::vector<uint8_t> fetch_cper_data(const std::string& additional_data_uri);

    // ── CPAD submission ───────────────────────────────────────────────────

    /**
     * Submit a CPAD to the BMC via HTTP PUT.
     *
     * The BMC acknowledges receipt in the response; action completion is
     * confirmed asynchronously via a Platform Action Event CPER.
     */
    RedfishResponse submit_cpad(const std::string& cpad_uri, const CpadRecord& cpad);

    // ── Push-mode event parsing ───────────────────────────────────────────

    /**
     * Extract CperEvent objects from a Redfish EventMessage payload.
     * Non-RAS event records in the same payload are silently ignored.
     */
    static std::vector<CperEvent> parse_cper_events(const nlohmann::json& event_payload);

private:
    IHttpClient&                              http_;
    const AuthState&                          auth_state_;
    const std::map<std::string, std::string>& discovery_map_;

    std::string service_uri() const;
    std::string event_subscriptions_uri() const;

};

} // namespace redfish
