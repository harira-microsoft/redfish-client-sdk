use crate::errors::RedfishError;
use crate::transport::types::{AuthMode, AuthState, Credentials};
use crate::transport::http_client::HttpClient;
use std::collections::HashMap;
use base64::Engine;

pub(crate) struct AuthManager<'a> {
    pub(crate) http:        &'a dyn HttpClient,
    pub(crate) credentials: Credentials,
    pub(crate) mode:        AuthMode,
    pub(crate) base_path:   String,
}

impl<'a> AuthManager<'a> {
    pub(crate) fn new(
        http:        &'a dyn HttpClient,
        credentials: Credentials,
        mode:        AuthMode,
        base_path:   &str,
    ) -> Self {
        Self { http, credentials, mode, base_path: base_path.to_string() }
    }

    /// Authenticate and return an AuthState.
    pub(crate) async fn authenticate(&self) -> Result<AuthState, RedfishError> {
        match self.mode {
            AuthMode::Session    => self.session_auth().await,
            AuthMode::Stateless  => self.stateless_auth().await,
        }
    }

    async fn session_auth(&self) -> Result<AuthState, RedfishError> {
        let session_uri = format!("{}/SessionService/Sessions", self.base_path);
        let body = serde_json::json!({
            "UserName": self.credentials.username,
            "Password": self.credentials.password,
        });

        let raw = self.http.request("POST", &session_uri, HashMap::new(), Some(body)).await?;

        if raw.status_code != 201 {
            return Err(RedfishError::AuthFailed(format!(
                "Session POST returned {}", raw.status_code
            )));
        }

        let token = raw.headers.get("x-auth-token")
            .or_else(|| raw.headers.get("X-Auth-Token"))
            .cloned()
            .ok_or_else(|| RedfishError::AuthFailed("No X-Auth-Token in response".into()))?;

        let uri = raw.headers.get("location")
            .or_else(|| raw.headers.get("Location"))
            .cloned();

        tracing::debug!("Session auth OK — token obtained, session_uri={:?}", uri);

        Ok(AuthState {
            mode:          AuthMode::Session,
            session_token: Some(token),
            session_uri:   uri,
            credentials:   self.credentials.clone(),
        })
    }

    async fn stateless_auth(&self) -> Result<AuthState, RedfishError> {
        // Validate credentials with a GET /redfish/v1
        let mut headers = HashMap::new();
        let encoded = base64::engine::general_purpose::STANDARD
            .encode(format!("{}:{}", self.credentials.username, self.credentials.password));
        headers.insert("Authorization".into(), format!("Basic {encoded}"));

        let raw = self.http.request("GET", &self.base_path, headers, None).await?;

        if raw.status_code == 401 || raw.status_code == 403 {
            return Err(RedfishError::AuthFailed(format!(
                "Stateless auth rejected ({})", raw.status_code
            )));
        }

        tracing::debug!("Stateless auth OK");

        Ok(AuthState {
            mode:          AuthMode::Stateless,
            session_token: None,
            session_uri:   None,
            credentials:   self.credentials.clone(),
        })
    }

    /// Attach auth headers to a request header map.
    pub(crate) fn attach_auth(state: &AuthState, headers: &mut HashMap<String, String>) {
        match state.mode {
            AuthMode::Session => {
                if let Some(ref token) = state.session_token {
                    headers.insert("X-Auth-Token".into(), token.clone());
                }
            }
            AuthMode::Stateless => {
                let encoded = base64::engine::general_purpose::STANDARD.encode(
                    format!("{}:{}", state.credentials.username, state.credentials.password)
                );
                headers.insert("Authorization".into(), format!("Basic {encoded}"));
            }
        }
    }

    /// Logout a session. Best-effort — errors are logged but not returned.
    pub(crate) async fn logout(http: &dyn HttpClient, state: &AuthState) {
        if state.mode != AuthMode::Session {
            return;
        }
        if let Some(ref uri) = state.session_uri {
            let mut headers = HashMap::new();
            Self::attach_auth(state, &mut headers);
            if let Err(e) = http.request("DELETE", uri, headers, None).await {
                tracing::warn!("Session logout failed (ignored): {}", e);
            } else {
                tracing::debug!("Session logged out");
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

    fn creds() -> Credentials { Credentials::new("admin", "password") }

    fn session_raw(status: u16, token: Option<&str>, location: Option<&str>) -> RawHttpResponse {
        let mut headers = HashMap::new();
        if let Some(t) = token   { headers.insert("x-auth-token".into(), t.into()); }
        if let Some(l) = location { headers.insert("location".into(), l.into()); }
        RawHttpResponse { status_code: status, headers, body_text: String::new(), body_json: None }
    }

    fn raw_ok() -> RawHttpResponse {
        RawHttpResponse { status_code: 200, headers: HashMap::new(),
                          body_text: String::new(), body_json: None }
    }

    fn raw_reject(code: u16) -> RawHttpResponse {
        RawHttpResponse { status_code: code, headers: HashMap::new(),
                          body_text: String::new(), body_json: None }
    }

    // ── Session auth ─────────────────────────────────────────────────────────

    #[tokio::test]
    async fn session_auth_success() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("POST", "/redfish/v1/SessionService/Sessions",
            session_raw(201, Some("abc123"),
                        Some("/redfish/v1/SessionService/Sessions/1")));
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Session, "/redfish/v1");
        let state = mgr.authenticate().await.unwrap();
        assert_eq!(state.mode, AuthMode::Session);
        assert_eq!(state.session_token, Some("abc123".into()));
        assert_eq!(state.session_uri,
                   Some("/redfish/v1/SessionService/Sessions/1".into()));
    }

    #[tokio::test]
    async fn session_auth_non_201_returns_error() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("POST", "/redfish/v1/SessionService/Sessions",
            session_raw(401, None, None));
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Session, "/redfish/v1");
        assert!(mgr.authenticate().await.is_err());
    }

    #[tokio::test]
    async fn session_auth_missing_token_returns_error() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        // 201 but no X-Auth-Token header — must fail
        mock.add("POST", "/redfish/v1/SessionService/Sessions",
            session_raw(201, None, None));
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Session, "/redfish/v1");
        assert!(mgr.authenticate().await.is_err());
    }

    #[tokio::test]
    async fn session_auth_no_location_still_succeeds() {
        // Location is optional; token is what matters
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("POST", "/redfish/v1/SessionService/Sessions",
            session_raw(201, Some("tok"), None));
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Session, "/redfish/v1");
        let state = mgr.authenticate().await.unwrap();
        assert!(state.session_uri.is_none());
        assert_eq!(state.session_token, Some("tok".into()));
    }

    // ── Stateless auth ───────────────────────────────────────────────────────

    #[tokio::test]
    async fn stateless_auth_success() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", raw_ok());
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Stateless, "/redfish/v1");
        let state = mgr.authenticate().await.unwrap();
        assert_eq!(state.mode, AuthMode::Stateless);
        assert!(state.session_token.is_none());
        assert!(state.session_uri.is_none());
    }

    #[tokio::test]
    async fn stateless_auth_401_returns_error() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", raw_reject(401));
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Stateless, "/redfish/v1");
        assert!(mgr.authenticate().await.is_err());
    }

    #[tokio::test]
    async fn stateless_auth_403_returns_error() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", raw_reject(403));
        let mgr = AuthManager::new(&mock, creds(), AuthMode::Stateless, "/redfish/v1");
        assert!(mgr.authenticate().await.is_err());
    }

    // ── attach_auth ──────────────────────────────────────────────────────────

    #[test]
    fn attach_auth_session_adds_token_header() {
        let state = AuthState {
            mode:          AuthMode::Session,
            session_token: Some("tok-xyz".into()),
            session_uri:   None,
            credentials:   creds(),
        };
        let mut headers = HashMap::new();
        AuthManager::attach_auth(&state, &mut headers);
        assert_eq!(headers.get("X-Auth-Token"), Some(&"tok-xyz".to_string()));
        assert!(!headers.contains_key("Authorization"));
    }

    #[test]
    fn attach_auth_session_with_no_token_adds_nothing() {
        let state = AuthState {
            mode:          AuthMode::Session,
            session_token: None,
            session_uri:   None,
            credentials:   creds(),
        };
        let mut headers = HashMap::new();
        AuthManager::attach_auth(&state, &mut headers);
        assert!(!headers.contains_key("X-Auth-Token"));
        assert!(!headers.contains_key("Authorization"));
    }

    #[test]
    fn attach_auth_stateless_adds_basic_header() {
        let state = AuthState {
            mode:          AuthMode::Stateless,
            session_token: None,
            session_uri:   None,
            credentials:   creds(),
        };
        let mut headers = HashMap::new();
        AuthManager::attach_auth(&state, &mut headers);
        let auth = headers.get("Authorization").expect("Authorization header missing");
        assert!(auth.starts_with("Basic "));
        let encoded = auth.strip_prefix("Basic ").unwrap();
        let decoded = String::from_utf8(
            base64::engine::general_purpose::STANDARD.decode(encoded).unwrap()
        ).unwrap();
        assert_eq!(decoded, "admin:password");
        assert!(!headers.contains_key("X-Auth-Token"));
    }

    #[test]
    fn attach_auth_stateless_different_creds_encode_correctly() {
        let state = AuthState {
            mode:          AuthMode::Stateless,
            session_token: None,
            session_uri:   None,
            credentials:   Credentials::new("user2", "s3cr3t"),
        };
        let mut headers = HashMap::new();
        AuthManager::attach_auth(&state, &mut headers);
        let auth = headers["Authorization"].strip_prefix("Basic ").unwrap();
        let decoded = String::from_utf8(
            base64::engine::general_purpose::STANDARD.decode(auth).unwrap()
        ).unwrap();
        assert_eq!(decoded, "user2:s3cr3t");
    }
}
