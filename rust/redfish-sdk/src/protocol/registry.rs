use crate::errors::RedfishError;
use crate::protocol::response::RedfishMessage;
use crate::transport::http_client::HttpClient;
use crate::transport::types::AuthState;
use crate::transport::auth::AuthManager;
use std::collections::HashMap;

/// Fetches and caches DMTF message registries from the BMC.
/// Used internally by service handles and EventListener for MessageId decoding.
#[allow(dead_code)]
pub(crate) struct MessageRegistry<'a> {
    http:     &'a dyn HttpClient,
    state:    &'a AuthState,
    base:     String,
    cache:    HashMap<String, serde_json::Value>,
}

#[allow(dead_code)]
impl<'a> MessageRegistry<'a> {
    pub(crate) fn new(http: &'a dyn HttpClient, state: &'a AuthState, base_path: &str) -> Self {
        Self { http, state, base: base_path.to_string(), cache: HashMap::new() }
    }

    /// Resolve a full MessageId string (e.g. "Base.1.8.Success") to a RedfishMessage.
    pub(crate) async fn resolve(&mut self, message_id: &str) -> Option<RedfishMessage> {
        // MessageId format: RegistryPrefix.Major.Minor.Key
        let parts: Vec<&str> = message_id.splitn(4, '.').collect();
        if parts.len() < 4 { return None; }
        let prefix = parts[0];
        let key    = parts[3];

        if !self.cache.contains_key(prefix) {
            let _ = self.fetch(prefix).await;
        }

        let registry = self.cache.get(prefix)?;
        let entry    = registry.get("Messages")?.get(key)?;

        Some(RedfishMessage {
            message_id:   message_id.to_string(),
            message:      entry.get("Message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            severity:     entry.get("Severity").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            resolution:   entry.get("Resolution").and_then(|v| v.as_str()).map(String::from),
            message_args: vec![],
        })
    }

    /// Fetch a registry by prefix and insert into cache. Returns true on success.
    pub(crate) async fn fetch(&mut self, prefix: &str) -> Result<bool, RedfishError> {
        let uri = format!("{}/Registries/{}/{}.json", self.base, prefix, prefix);
        let mut headers = HashMap::new();
        AuthManager::attach_auth(self.state, &mut headers);
        let raw = self.http.request("GET", &uri, headers, None).await?;
        if raw.status_code == 200 {
            if let Some(body) = raw.body_json {
                self.cache.insert(prefix.to_string(), body);
                return Ok(true);
            }
        }
        Ok(false)
    }
}
