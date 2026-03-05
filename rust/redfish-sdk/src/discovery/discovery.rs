use std::collections::HashMap;
use crate::errors::RedfishError;
use crate::transport::{HttpClient, AuthState};
use crate::transport::auth::AuthManager;

/// Result of a discovery call — inspectable map of service names → URIs.
#[derive(Debug, Default)]
pub struct DiscoveryResult {
    pub services:     HashMap<String, String>,
    pub capabilities: Vec<String>,
    pub raw:          Option<serde_json::Value>,
}

impl DiscoveryResult {
    pub fn has_service(&self, name: &str) -> bool {
        self.services.contains_key(name)
    }
    pub fn service_uri(&self, name: &str) -> Option<&str> {
        self.services.get(name).map(String::as_str)
    }
}

/// Discovery handle — borrows the context.
pub struct Discovery<'ctx> {
    pub(crate) http:      &'ctx dyn HttpClient,
    pub(crate) state:     &'ctx AuthState,
    pub(crate) base_path: String,
    pub(crate) disc_map:  &'ctx std::sync::Mutex<HashMap<String, String>>,
}

impl<'ctx> Discovery<'ctx> {
    // ── Async ────────────────────────────────────────────────────────────────

    /// GET ServiceRoot only — enumerate top-level links, no traversal.
    pub async fn root(&self) -> Result<DiscoveryResult, RedfishError> {
        let body = self.get_root().await?;
        let result = self.parse_root(&body);
        self.update_map(&result);
        Ok(result)
    }

    /// GET ServiceRoot, then GET the named service only.
    pub async fn partial(&self, service: &str) -> Result<DiscoveryResult, RedfishError> {
        let root_body = self.get_root().await?;
        let mut result = self.parse_root(&root_body);

        if let Some(uri) = result.service_uri(service).map(String::from) {
            self.get_one(&mut result, service, &uri).await?;
        }

        self.update_map(&result);
        Ok(result)
    }

    /// GET ServiceRoot, then GET all top-level service links one level deep.
    pub async fn full(&self) -> Result<DiscoveryResult, RedfishError> {
        let root_body = self.get_root().await?;
        let mut result = self.parse_root(&root_body);

        let uris: Vec<(String, String)> = result.services
            .iter()
            .map(|(k, v)| (k.clone(), v.clone()))
            .collect();

        for (name, uri) in uris {
            let _ = self.get_one(&mut result, &name, &uri).await;
        }

        self.update_map(&result);
        Ok(result)
    }

    // ── Blocking wrappers ────────────────────────────────────────────────────

    pub fn root_blocking(&self) -> Result<DiscoveryResult, RedfishError> {
        tokio::runtime::Runtime::new()
            .map_err(|e| RedfishError::IoError(e.to_string()))?
            .block_on(self.root())
    }

    pub fn partial_blocking(&self, service: &str) -> Result<DiscoveryResult, RedfishError> {
        tokio::runtime::Runtime::new()
            .map_err(|e| RedfishError::IoError(e.to_string()))?
            .block_on(self.partial(service))
    }

    pub fn full_blocking(&self) -> Result<DiscoveryResult, RedfishError> {
        tokio::runtime::Runtime::new()
            .map_err(|e| RedfishError::IoError(e.to_string()))?
            .block_on(self.full())
    }

    // ── Helpers ──────────────────────────────────────────────────────────────

    async fn get_root(&self) -> Result<serde_json::Value, RedfishError> {
        let mut headers = HashMap::new();
        AuthManager::attach_auth(self.state, &mut headers);
        let raw = self.http.request("GET", &self.base_path, headers, None).await?;
        raw.body_json.ok_or_else(|| RedfishError::ProtocolError("Empty ServiceRoot response".into()))
    }

    fn parse_root(&self, body: &serde_json::Value) -> DiscoveryResult {
        let mut services: HashMap<String, String> = HashMap::new();

        // Walk top-level keys that contain {"@odata.id": "..."}
        if let Some(obj) = body.as_object() {
            for (key, val) in obj {
                if key.starts_with('@') || key.starts_with('_') { continue; }
                if let Some(id) = val.get("@odata.id").and_then(|v| v.as_str()) {
                    services.insert(key.clone(), id.to_string());
                }
            }
        }

        let capabilities: Vec<String> = services.keys().cloned().collect();

        DiscoveryResult { services, capabilities, raw: Some(body.clone()) }
    }

    async fn get_one(
        &self,
        result: &mut DiscoveryResult,
        name:   &str,
        uri:    &str,
    ) -> Result<(), RedfishError> {
        let mut headers = HashMap::new();
        AuthManager::attach_auth(self.state, &mut headers);
        let raw = self.http.request("GET", uri, headers, None).await?;
        if let Some(body) = raw.body_json {
            // If the service has sub-collections, map them too
            if let Some(obj) = body.as_object() {
                for (key, val) in obj {
                    if key.starts_with('@') { continue; }
                    if let Some(id) = val.get("@odata.id").and_then(|v| v.as_str()) {
                        let sub_name = format!("{}/{}", name, key);
                        result.services.entry(sub_name).or_insert_with(|| id.to_string());
                    }
                }
            }
        }
        Ok(())
    }

    fn update_map(&self, result: &DiscoveryResult) {
        if let Ok(mut map) = self.disc_map.lock() {
            for (k, v) in &result.services {
                map.insert(k.clone(), v.clone());
            }
        }
    }
}

// ── Unit tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::transport::http_client::MockHttpClient;
    use crate::transport::types::{AuthMode, AuthState, Credentials, RawHttpResponse};

    fn anon_state() -> AuthState {
        AuthState {
            mode:          AuthMode::Stateless,
            session_token: None,
            session_uri:   None,
            credentials:   Credentials::new("admin", "password"),
        }
    }

    fn root_body() -> serde_json::Value {
        serde_json::json!({
            "@odata.id":      "/redfish/v1",
            "@odata.type":    "#ServiceRoot.v1_5_0.ServiceRoot",
            "Systems":        { "@odata.id": "/redfish/v1/Systems" },
            "Chassis":        { "@odata.id": "/redfish/v1/Chassis" },
            "Managers":       { "@odata.id": "/redfish/v1/Managers" },
            "SessionService": { "@odata.id": "/redfish/v1/SessionService" },
            "EventService":   { "@odata.id": "/redfish/v1/EventService" },
            "UpdateService":  { "@odata.id": "/redfish/v1/UpdateService" },
        })
    }

    fn root_mock() -> MockHttpClient {
        let body = root_body();
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", RawHttpResponse {
            status_code: 200,
            headers:     HashMap::new(),
            body_text:   body.to_string(),
            body_json:   Some(body),
        });
        mock
    }

    fn make_disc<'a>(
        mock:     &'a MockHttpClient,
        state:    &'a AuthState,
        disc_map: &'a std::sync::Mutex<HashMap<String, String>>,
    ) -> Discovery<'a> {
        Discovery {
            http:      mock,
            state,
            base_path: "/redfish/v1".to_string(),
            disc_map,
        }
    }

    #[tokio::test]
    async fn root_populates_top_level_services() {
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let mock     = root_mock();
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert!(result.has_service("Systems"),        "Systems missing");
        assert!(result.has_service("Chassis"),        "Chassis missing");
        assert!(result.has_service("Managers"),       "Managers missing");
        assert!(result.has_service("EventService"),   "EventService missing");
        assert!(result.has_service("UpdateService"),  "UpdateService missing");
        assert!(result.has_service("SessionService"), "SessionService missing");
    }

    #[tokio::test]
    async fn root_correct_service_uris() {
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let mock     = root_mock();
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert_eq!(result.service_uri("Systems"),     Some("/redfish/v1/Systems"));
        assert_eq!(result.service_uri("Chassis"),     Some("/redfish/v1/Chassis"));
        assert_eq!(result.service_uri("EventService"),Some("/redfish/v1/EventService"));
    }

    #[tokio::test]
    async fn root_skips_odata_annotation_keys() {
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let mock     = root_mock();
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert!(!result.services.contains_key("@odata.id"),   "@odata.id leaked");
        assert!(!result.services.contains_key("@odata.type"), "@odata.type leaked");
    }

    #[tokio::test]
    async fn root_skips_underscore_keys() {
        let mut body = root_body();
        body["_internal"] = serde_json::json!({"@odata.id": "/redfish/v1/Internal"});
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", RawHttpResponse {
            status_code: 200, headers: HashMap::new(),
            body_text:   body.to_string(), body_json: Some(body),
        });
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert!(!result.services.contains_key("_internal"),
                "_internal should be skipped");
    }

    #[tokio::test]
    async fn root_ignores_keys_without_odata_id() {
        // A key present but its value has no @odata.id should not appear
        let body = serde_json::json!({
            "Systems": { "@odata.id": "/redfish/v1/Systems" },
            "Name": "MyBMC",   // plain string, no @odata.id
        });
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", RawHttpResponse {
            status_code: 200, headers: HashMap::new(),
            body_text:   body.to_string(), body_json: Some(body),
        });
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert!( result.has_service("Systems"), "Systems should be present");
        assert!(!result.services.contains_key("Name"), "Name should be absent");
    }

    #[tokio::test]
    async fn update_map_persists_to_mutex() {
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let mock     = root_mock();
        make_disc(&mock, &state, &disc_map).root().await.unwrap();
        let guard = disc_map.lock().unwrap();
        assert!(guard.contains_key("Systems"), "disc_map not updated");
        assert!(guard.contains_key("Chassis"), "disc_map not updated");
    }

    #[tokio::test]
    async fn empty_root_yields_empty_services() {
        let body = serde_json::json!({});
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", RawHttpResponse {
            status_code: 200, headers: HashMap::new(),
            body_text:   "{}".into(), body_json: Some(body),
        });
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert!(result.services.is_empty());
    }

    #[tokio::test]
    async fn raw_body_stored_in_result() {
        let state    = anon_state();
        let disc_map = std::sync::Mutex::new(HashMap::new());
        let mock     = root_mock();
        let result   = make_disc(&mock, &state, &disc_map).root().await.unwrap();
        assert!(result.raw.is_some(), "raw body should be stored");
    }

    #[test]
    fn has_service_returns_false_for_missing_key() {
        let result = DiscoveryResult::default();
        assert!(!result.has_service("Systems"));
    }

    #[test]
    fn service_uri_returns_none_for_missing_key() {
        let result = DiscoveryResult::default();
        assert!(result.service_uri("Systems").is_none());
    }
}
