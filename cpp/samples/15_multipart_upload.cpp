/**
 * Sample 15 — Multipart Firmware Upload (v0.2)
 *
 * Demonstrates:
 *   - UpdateServiceHandle::push_firmware()  (FR7.5)
 *   - MockHttpClient for testing without a real BMC
 *
 * Usage:
 *   ./15_multipart_upload
 */

#include "redfish_sdk/transport/http_client.hpp"
#include "redfish_sdk/transport/auth.hpp"
#include "redfish_sdk/services/update_service.hpp"
#include "redfish_sdk/errors.hpp"
#include <fstream>
#include <iostream>
#include <map>
#include <nlohmann/json.hpp>
#include <string>

int main() {
    // ── Scenario 1: successful 202 push ────────────────────────────────────
    {
        redfish::MockHttpClient mock;

        // GET UpdateService → returns MultipartHttpPushUri
        redfish::RawHttpResponse svc_resp;
        svc_resp.status_code   = 200;
        svc_resp.body_json_str = R"({
            "MultipartHttpPushUri": "/redfish/v1/UpdateService/upload",
            "HttpPushUri": "/redfish/v1/UpdateService/push"
        })";
        svc_resp.body_text = svc_resp.body_json_str;
        svc_resp.is_json   = true;
        mock.register_response("GET", "/redfish/v1/UpdateService", svc_resp);

        // POST multipart → 202 Accepted
        redfish::RawHttpResponse upload_resp;
        upload_resp.status_code = 202;
        upload_resp.headers["location"] = "/redfish/v1/TaskService/Tasks/1";
        upload_resp.body_json_str = R"({"@odata.id":"/redfish/v1/TaskService/Tasks/1"})";
        upload_resp.body_text = upload_resp.body_json_str;
        upload_resp.is_json   = true;
        mock.register_response("POST", "/redfish/v1/UpdateService/upload", upload_resp);

        // Create a temporary dummy firmware file
        const std::string fw_path = "/tmp/test_firmware.bin";
        {
            std::ofstream f(fw_path, std::ios::binary);
            for (int i = 0; i < 64; ++i) f.put(static_cast<char>(i));
        }

        redfish::AuthState auth;
        auth.mode  = redfish::AuthMode::STATELESS;
        auth.credentials = {"admin", "admin"};

        std::map<std::string, std::string> disc_map{
            {"UpdateService", "/redfish/v1/UpdateService"}
        };

        redfish::UpdateServiceHandle update(mock, auth, disc_map);

        nlohmann::json params = {{"Targets", nlohmann::json::array()}, {"Oem", nullptr}};
        auto resp = update.push_firmware(fw_path, params);

        std::cout << "Scenario 1 — 202 push:\n"
                  << "  HTTP " << resp.status_code
                  << (resp.status_code == 202 ? " ✓" : " ✗") << "\n";

        // Verify multipart was the call used
        bool found_multipart = false;
        for (auto& c : mock.recorded_calls())
            if (c.method == "POST_MULTIPART") found_multipart = true;
        std::cout << "  Multipart call recorded: " << (found_multipart ? "✓" : "✗") << "\n";
    }

    // ── Scenario 2: no push URI → throws RedfishProtocolError ─────────────
    {
        redfish::MockHttpClient mock;

        redfish::RawHttpResponse svc_resp;
        svc_resp.status_code   = 200;
        svc_resp.body_json_str = R"({"ServiceEnabled": true})";
        svc_resp.body_text = svc_resp.body_json_str;
        svc_resp.is_json   = true;
        mock.register_response("GET", "/redfish/v1/UpdateService", svc_resp);

        redfish::AuthState auth;
        auth.mode  = redfish::AuthMode::STATELESS;
        auth.credentials = {"admin", "admin"};
        std::map<std::string, std::string> disc_map{{"UpdateService", "/redfish/v1/UpdateService"}};

        redfish::UpdateServiceHandle update(mock, auth, disc_map);

        bool threw = false;
        try {
            update.push_firmware("/tmp/test_firmware.bin");
        } catch (const redfish::RedfishProtocolError& e) {
            threw = true;
            std::cout << "\nScenario 2 — no push URI:\n"
                      << "  Correctly threw RedfishProtocolError: " << e.what() << " ✓\n";
        }
        if (!threw)
            std::cout << "\nScenario 2 — FAIL: should have thrown\n";
    }

    std::cout << "\n✓ Multipart upload sample complete\n";
    return 0;
}
