use std::sync::Arc;
use crate::errors::RedfishError;
use crate::transport::{DefaultHttpClient, AuthManager, EndpointCapabilities, ConnectionConfig, AuthMode, Credentials};
use crate::context::ClientContext;

/// Connect to a Redfish endpoint (async).
///
/// # Example
/// ```no_run
/// # #[tokio::main] async fn main() -> Result<(), Box<dyn std::error::Error>> {
/// let ctx = redfish_sdk::connect(
///     "127.0.0.1", 8000,
///     redfish_sdk::Credentials::new("admin", "admin"),
///     redfish_sdk::AuthMode::Session,
///     redfish_sdk::ConnectionConfig::default(),
/// ).await?;
/// # Ok(()) }
/// ```
pub async fn connect(
    host:        &str,
    port:        u16,
    credentials: Credentials,
    auth_mode:   AuthMode,
    config:      ConnectionConfig,
) -> Result<ClientContext, RedfishError> {
    let scheme    = if config.use_tls { "https" } else { "http" };
    let base_url  = format!("{scheme}://{host}:{port}");
    let base_path = config.base_path_override
        .clone()
        .unwrap_or_else(|| format!("{base_url}/redfish/v1"));

    let http = DefaultHttpClient::new(&base_url, &config)?;
    let http: Box<dyn crate::transport::HttpClient> = Box::new(http);

    let mgr = AuthManager::new(http.as_ref(), credentials.clone(), auth_mode.clone(), &base_path);
    let auth_state = mgr.authenticate().await?;

    // Probe capabilities from ServiceRoot
    let caps = probe_capabilities(http.as_ref(), &auth_state, &base_path).await;

    let runtime = Arc::new(
        tokio::runtime::Builder::new_multi_thread()
            .enable_all()
            .build()
            .map_err(|e| RedfishError::IoError(e.to_string()))?
    );

    Ok(ClientContext::new(http, auth_state, caps, config, base_path, runtime))
}

/// Blocking wrapper around `connect()`.
pub fn connect_blocking(
    host:        &str,
    port:        u16,
    credentials: Credentials,
    auth_mode:   AuthMode,
    config:      ConnectionConfig,
) -> Result<ClientContext, RedfishError> {
    tokio::runtime::Runtime::new()
        .map_err(|e| RedfishError::IoError(e.to_string()))?
        .block_on(connect(host, port, credentials, auth_mode, config))
}

// ── Internal helpers ─────────────────────────────────────────────────────────

async fn probe_capabilities(
    http:      &dyn crate::transport::HttpClient,
    state:     &crate::transport::AuthState,
    base_path: &str,
) -> EndpointCapabilities {
    let mut headers = std::collections::HashMap::new();
    crate::transport::auth::AuthManager::attach_auth(state, &mut headers);

    match http.request("GET", base_path, headers, None).await {
        Ok(raw) => {
            if let Some(body) = raw.body_json {
                let version = body.get("RedfishVersion")
                    .and_then(|v| v.as_str())
                    .unwrap_or("")
                    .to_string();
                let services = body.as_object()
                    .map(|obj| obj.keys().filter(|k| !k.starts_with('@')).cloned().collect())
                    .unwrap_or_default();
                return EndpointCapabilities {
                    redfish_version:    version,
                    odata_version:      raw.headers.get("odata-version").cloned().unwrap_or_default(),
                    available_services: services,
                };
            }
            EndpointCapabilities::default()
        }
        Err(e) => {
            tracing::warn!("Could not probe capabilities: {}", e);
            EndpointCapabilities::default()
        }
    }
}
