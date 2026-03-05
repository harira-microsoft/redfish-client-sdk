
/// Authentication mode for the connection.
#[derive(Debug, Clone, PartialEq, Eq)]
pub enum AuthMode {
    /// Session-based: POST /redfish/v1/SessionService/Sessions, use X-Auth-Token.
    Session,
    /// Stateless: Basic auth on every request.
    Stateless,
}

/// Username + password. Does not implement Debug to prevent accidental password logging.
#[derive(Clone)]
pub struct Credentials {
    pub username: String,
    pub password: String,
}

impl Credentials {
    pub fn new(username: impl Into<String>, password: impl Into<String>) -> Self {
        Self { username: username.into(), password: password.into() }
    }
}

impl std::fmt::Debug for Credentials {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        f.debug_struct("Credentials")
            .field("username", &self.username)
            .field("password", &"[REDACTED]")
            .finish()
    }
}

/// All SDK connection tunables. Use `ConnectionConfig::default()` for sane defaults.
#[derive(Debug, Clone)]
pub struct ConnectionConfig {
    /// Whether to use TLS (https). Default: true.
    pub use_tls:                       bool,
    /// Whether to verify the server's TLS certificate. Default: true.
    pub verify_tls:                    bool,
    pub tls_ca_cert:                   Option<String>,
    pub connect_timeout_secs:          f32,
    pub request_timeout_secs:          f32,
    pub task_poll_interval_secs:       f32,
    pub task_timeout_secs:             f32,
    pub base_path_override:            Option<String>,
    pub retry_on_connection_failure:   u32,
    pub retry_status_codes:            Vec<u16>,
    pub retry_delay_secs:              u64,
}

impl Default for ConnectionConfig {
    fn default() -> Self {
        Self {
            use_tls:                     true,
            verify_tls:                  true,
            tls_ca_cert:                 None,
            connect_timeout_secs:        10.0,
            request_timeout_secs:        30.0,
            task_poll_interval_secs:     5.0,
            task_timeout_secs:           300.0,
            base_path_override:          None,
            retry_on_connection_failure: 0,
            retry_status_codes:          vec![],
            retry_delay_secs:            2,
        }
    }
}

/// Negotiated endpoint capabilities populated after connect().
#[derive(Debug, Clone, Default)]
pub struct EndpointCapabilities {
    pub redfish_version:    String,
    pub odata_version:      String,
    pub available_services: Vec<String>,
}

/// Internal timeout config derived from ConnectionConfig.
#[derive(Debug, Clone)]
pub(crate) struct TimeoutConfig {
    pub(crate) connect_secs: f32,
    pub(crate) request_secs: f32,
}

impl From<&ConnectionConfig> for TimeoutConfig {
    fn from(c: &ConnectionConfig) -> Self {
        Self {
            connect_secs: c.connect_timeout_secs,
            request_secs: c.request_timeout_secs,
        }
    }
}

/// Current auth session state — held privately in ClientContext.
#[derive(Debug, Clone)]
pub(crate) struct AuthState {
    pub(crate) mode:          AuthMode,
    pub(crate) session_token: Option<String>,
    pub(crate) session_uri:   Option<String>,
    pub(crate) credentials:   Credentials,
}

/// Raw HTTP response before promotion to RedfishResponse.
#[derive(Debug)]
pub(crate) struct RawHttpResponse {
    pub(crate) status_code: u16,
    pub(crate) headers:     std::collections::HashMap<String, String>,
    pub(crate) body_text:   String,
    pub(crate) body_json:   Option<serde_json::Value>,
}
