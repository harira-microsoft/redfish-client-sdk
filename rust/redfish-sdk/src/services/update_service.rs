// SPDX-License-Identifier: MIT
// Copyright (c) Microsoft Corporation. All rights reserved.

use crate::context::ClientContext;
use crate::errors::RedfishError;
use crate::protocol::response::RedfishResponse;

pub struct UpdateServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> UpdateServiceHandle<'ctx> {
    pub(crate) fn new(ctx: &'ctx ClientContext) -> Self { Self { ctx } }

    fn service_uri(&self) -> String {
        self.ctx.resolve_service_uri("UpdateService", "/UpdateService")
    }

    // ── Async ────────────────────────────────────────────────────────────────

    pub async fn get_service_info(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(&self.service_uri()).await
    }

    pub async fn list_firmware_inventory(&self) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/FirmwareInventory", self.service_uri());
        self.ctx.get(&uri).await
    }

    pub async fn get_firmware_component(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(uri).await
    }

    pub async fn list_software_inventory(&self) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/SoftwareInventory", self.service_uri());
        self.ctx.get(&uri).await
    }

    pub async fn get_software_component(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(uri).await
    }

    /// SimpleUpdate — returns RedfishResponse; `response.task` is `Some` if the BMC returned 202.
    pub async fn simple_update(
        &self,
        image_uri:         &str,
        targets:           Vec<String>,
        transfer_protocol: Option<&str>,
        apply_time:        Option<&str>,
    ) -> Result<RedfishResponse, RedfishError> {
        let action_uri = format!("{}/Actions/UpdateService.SimpleUpdate", self.service_uri());
        let mut body = serde_json::json!({
            "ImageURI": image_uri,
            "Targets":  targets,
        });
        if let Some(tp) = transfer_protocol { body["TransferProtocol"] = serde_json::json!(tp); }
        if let Some(at) = apply_time        { body["ApplyOptions"] = serde_json::json!({ "ApplyTime": at }); }

        self.ctx.post(&action_uri, body).await
    }

    /// Multipart push upload — sends the firmware binary via multipart/form-data.
    pub async fn push_firmware(
        &self,
        file_path: &str,
        targets:   Vec<String>,
    ) -> Result<RedfishResponse, RedfishError> {
        use crate::transport::auth::AuthManager;
        use std::collections::HashMap;

        let action_uri = format!("{}/Actions/UpdateService.SimpleUpdate", self.service_uri());

        let file_bytes = std::fs::read(file_path)
            .map_err(|e| RedfishError::IoError(e.to_string()))?;
        let filename = std::path::Path::new(file_path)
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("firmware.bin")
            .to_string();

        // Build a raw multipart request via reqwest directly (bypass DefaultHttpClient for multipart)
        let targets_json = serde_json::json!({ "Targets": targets }).to_string();

        let part_params = reqwest::multipart::Part::text(targets_json)
            .mime_str("application/json")
            .map_err(|e| RedfishError::IoError(e.to_string()))?;
        let part_file = reqwest::multipart::Part::bytes(file_bytes)
            .file_name(filename)
            .mime_str("application/octet-stream")
            .map_err(|e| RedfishError::IoError(e.to_string()))?;

        let form = reqwest::multipart::Form::new()
            .part("UpdateParameters", part_params)
            .part("UpdateFile", part_file);

        let mut headers = HashMap::new();
        AuthManager::attach_auth(&self.ctx.auth_state, &mut headers);

        // Build reqwest client inline for multipart (DefaultHttpClient doesn't expose it)
        let client = reqwest::Client::builder()
            .danger_accept_invalid_certs(!self.ctx.config.verify_tls)
            .build()
            .map_err(|e| RedfishError::ConnectionFailed(e.to_string()))?;

        let full_url = if action_uri.starts_with("http") {
            action_uri.clone()
        } else {
            format!("{}{}", self.ctx.http.base_url(), action_uri)
        };

        let mut req = client.post(&full_url).multipart(form);
        for (k, v) in &headers {
            req = req.header(k.as_str(), v.as_str());
        }

        let resp = req.send().await.map_err(RedfishError::from)?;
        let status = resp.status().as_u16();
        let hdrs: std::collections::HashMap<String,String> = resp.headers().iter()
            .map(|(k,v)| (k.to_string(), v.to_str().unwrap_or("").to_string()))
            .collect();
        let text = resp.text().await.unwrap_or_default();
        let json = serde_json::from_str(&text).ok();

        Ok(RedfishResponse::from_raw(crate::transport::types::RawHttpResponse {
            status_code: status, headers: hdrs, body_text: text, body_json: json,
        }))
    }

    // ── Blocking wrappers ────────────────────────────────────────────────────

    pub fn get_service_info_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_service_info())
    }
    pub fn list_firmware_inventory_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_firmware_inventory())
    }
    pub fn get_firmware_component_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_firmware_component(uri))
    }
    pub fn list_software_inventory_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_software_inventory())
    }
    pub fn get_software_component_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_software_component(uri))
    }
    pub fn simple_update_blocking(
        &self, image_uri: &str, targets: Vec<String>,
        transfer_protocol: Option<&str>, apply_time: Option<&str>,
    ) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.simple_update(image_uri, targets, transfer_protocol, apply_time))
    }
    pub fn push_firmware_blocking(&self, file_path: &str, targets: Vec<String>) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.push_firmware(file_path, targets))
    }
}
