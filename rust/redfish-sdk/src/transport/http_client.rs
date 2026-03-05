use crate::transport::types::{ConnectionConfig, RawHttpResponse, TimeoutConfig};
use crate::errors::RedfishError;
use std::collections::HashMap;
use std::time::Duration;
use async_trait::async_trait;

// ── Trait ───────────────────────────────────────────────────────────────────

/// Contract used by all service handles and ClientContext for HTTP requests.
/// The trait makes the transport layer swappable for tests.
#[async_trait]
pub(crate) trait HttpClient: Send + Sync {
    async fn request(
        &self,
        method:  &str,
        path:    &str,
        headers: HashMap<String, String>,
        body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError>;

    fn base_url(&self) -> &str;
}

// ── Production implementation ────────────────────────────────────────────────

pub(crate) struct DefaultHttpClient {
    client:       reqwest::Client,
    base_url:     String,
    retry_conn:   u32,
    retry_codes:  Vec<u16>,
    retry_delay:  Duration,
}

impl DefaultHttpClient {
    pub(crate) fn new(
        base_url: &str,
        config:   &ConnectionConfig,
    ) -> Result<Self, RedfishError> {
        let tc = TimeoutConfig::from(config);
        let mut builder = reqwest::Client::builder()
            .connection_verbose(false)
            .timeout(Duration::from_secs_f32(tc.request_secs))
            .connect_timeout(Duration::from_secs_f32(tc.connect_secs));

        if !config.verify_tls {
            builder = builder.danger_accept_invalid_certs(true);
        } else if let Some(ref ca_path) = config.tls_ca_cert {
            let pem = std::fs::read(ca_path)
                .map_err(|e| RedfishError::TlsError(e.to_string()))?;
            let cert = reqwest::Certificate::from_pem(&pem)
                .map_err(|e| RedfishError::TlsError(e.to_string()))?;
            builder = builder.add_root_certificate(cert);
        }

        let client = builder.build()
            .map_err(|e| RedfishError::ConnectionFailed(e.to_string()))?;

        Ok(Self {
            client,
            base_url: base_url.to_string(),
            retry_conn:  config.retry_on_connection_failure,
            retry_codes: config.retry_status_codes.clone(),
            retry_delay: Duration::from_secs(config.retry_delay_secs),
        })
    }

    /// Build a full URL from a path (already absolute) or relative to base_url.
    fn full_url(&self, path: &str) -> String {
        if path.starts_with("http://") || path.starts_with("https://") {
            path.to_string()
        } else {
            format!("{}{}", self.base_url, path)
        }
    }

    async fn execute_with_retry(
        &self,
        method:  &str,
        path:    &str,
        headers: HashMap<String, String>,
        body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError> {
        let url = self.full_url(path);
        let mut attempts = 0u32;
        loop {
            let result = self.execute_once(method, &url, &headers, body.clone()).await;
            match &result {
                Err(RedfishError::ConnectionFailed(_)) if attempts < self.retry_conn => {
                    attempts += 1;
                    tracing::debug!("Connection retry {}/{} for {}", attempts, self.retry_conn, url);
                    tokio::time::sleep(self.retry_delay).await;
                    continue;
                }
                Ok(raw) if self.retry_codes.contains(&raw.status_code) && attempts < self.retry_conn => {
                    attempts += 1;
                    tracing::debug!("Status-code retry {}/{} (status={}) for {}", attempts, self.retry_conn, raw.status_code, url);
                    tokio::time::sleep(self.retry_delay).await;
                    continue;
                }
                _ => return result,
            }
        }
    }

    async fn execute_once(
        &self,
        method:  &str,
        url:     &str,
        headers: &HashMap<String, String>,
        body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError> {
        let mut req = match method.to_uppercase().as_str() {
            "GET"    => self.client.get(url),
            "POST"   => self.client.post(url),
            "PATCH"  => self.client.patch(url),
            "DELETE" => self.client.delete(url),
            "HEAD"   => self.client.head(url),
            other    => return Err(RedfishError::ProtocolError(format!("Unknown method: {other}"))),
        };

        // Standard Redfish headers
        req = req
            .header("OData-Version", "4.0")
            .header("Accept",        "application/json")
            .header("Content-Type",  "application/json");

        for (k, v) in headers {
            req = req.header(k.as_str(), v.as_str());
        }

        if let Some(ref json) = body {
            req = req.json(json);
        }

        let resp = req.send().await.map_err(RedfishError::from)?;
        let status = resp.status().as_u16();
        let hdrs: HashMap<String, String> = resp
            .headers()
            .iter()
            .map(|(k, v)| (k.to_string(), v.to_str().unwrap_or("").to_string()))
            .collect();
        let text = resp.text().await.unwrap_or_default();
        let json = serde_json::from_str(&text).ok();

        Ok(RawHttpResponse { status_code: status, headers: hdrs, body_text: text, body_json: json })
    }
}

#[async_trait]
impl HttpClient for DefaultHttpClient {
    async fn request(
        &self,
        method:  &str,
        path:    &str,
        headers: HashMap<String, String>,
        body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError> {
        self.execute_with_retry(method, path, headers, body).await
    }

    fn base_url(&self) -> &str {
        &self.base_url
    }
}

// ── Test double ─────────────────────────────────────────────────────────────

#[cfg(test)]
pub(crate) struct MockHttpClient {
    pub responses: std::collections::HashMap<(String, String), RawHttpResponse>,
    pub base_url:  String,
}

#[cfg(test)]
impl MockHttpClient {
    pub fn new(base_url: &str) -> Self {
        Self { responses: Default::default(), base_url: base_url.to_string() }
    }

    pub fn add(&mut self, method: &str, path: &str, raw: RawHttpResponse) {
        self.responses.insert((method.to_uppercase(), path.to_string()), raw);
    }
}

#[cfg(test)]
#[async_trait]
impl HttpClient for MockHttpClient {
    async fn request(
        &self,
        method:  &str,
        path:    &str,
        _headers: HashMap<String, String>,
        _body:    Option<serde_json::Value>,
    ) -> Result<RawHttpResponse, RedfishError> {
        self.responses
            .get(&(method.to_uppercase(), path.to_string()))
            .map(|r| RawHttpResponse {
                status_code: r.status_code,
                headers:     r.headers.clone(),
                body_text:   r.body_text.clone(),
                body_json:   r.body_json.clone(),
            })
            .ok_or_else(|| RedfishError::HttpError { status_code: 404, message: format!("Mock: no entry for {} {}", method, path) })
    }

    fn base_url(&self) -> &str { &self.base_url }
}

// ── Unit tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    fn ok_raw(body: serde_json::Value) -> RawHttpResponse {
        RawHttpResponse {
            status_code: 200,
            headers:     HashMap::new(),
            body_text:   body.to_string(),
            body_json:   Some(body),
        }
    }

    #[tokio::test]
    async fn mock_hit_returns_registered_response() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", ok_raw(serde_json::json!({"@odata.id": "/redfish/v1"})));
        let raw = mock.request("GET", "/redfish/v1", HashMap::new(), None).await.unwrap();
        assert_eq!(raw.status_code, 200);
        assert!(raw.body_json.is_some());
    }

    #[tokio::test]
    async fn mock_miss_returns_404_error() {
        let mock = MockHttpClient::new("http://localhost:8000");
        let result = mock.request("GET", "/redfish/v1/Missing", HashMap::new(), None).await;
        assert!(result.is_err());
        match result {
            Err(crate::errors::RedfishError::HttpError { status_code, .. }) => {
                assert_eq!(status_code, 404);
            }
            other => panic!("Expected HttpError 404, got {:?}", other),
        }
    }

    #[tokio::test]
    async fn mock_method_case_insensitive() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", ok_raw(serde_json::json!({})));
        // Registered as "GET"; call with lowercase "get" — must match
        let result = mock.request("get", "/redfish/v1", HashMap::new(), None).await;
        assert!(result.is_ok());
    }

    #[test]
    fn mock_base_url_returned() {
        let mock = MockHttpClient::new("http://bmc.example.com:8000");
        assert_eq!(mock.base_url(), "http://bmc.example.com:8000");
    }

    #[tokio::test]
    async fn mock_multiple_endpoints_independent() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET",  "/redfish/v1",
                 ok_raw(serde_json::json!({"root": true})));
        mock.add("GET",  "/redfish/v1/Systems",
                 ok_raw(serde_json::json!({"systems": true})));
        mock.add("POST", "/redfish/v1/SessionService/Sessions", RawHttpResponse {
            status_code: 201,
            headers: {
                let mut h = HashMap::new();
                h.insert("x-auth-token".into(), "tok".into());
                h
            },
            body_text: String::new(),
            body_json: None,
        });

        let r1 = mock.request("GET",  "/redfish/v1",
                              HashMap::new(), None).await.unwrap();
        let r2 = mock.request("GET",  "/redfish/v1/Systems",
                              HashMap::new(), None).await.unwrap();
        let r3 = mock.request("POST", "/redfish/v1/SessionService/Sessions",
                              HashMap::new(), None).await.unwrap();

        assert_eq!(r1.body_json.unwrap()["root"],    true);
        assert_eq!(r2.body_json.unwrap()["systems"], true);
        assert_eq!(r3.status_code, 201);
    }

    #[tokio::test]
    async fn mock_wrong_method_returns_error() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", ok_raw(serde_json::json!({})));
        // Registered GET, request POST — must miss
        let result = mock.request("POST", "/redfish/v1", HashMap::new(), None).await;
        assert!(result.is_err());
    }

    #[tokio::test]
    async fn mock_response_body_text_preserved() {
        let mut mock = MockHttpClient::new("http://localhost:8000");
        mock.add("GET", "/redfish/v1", RawHttpResponse {
            status_code: 200,
            headers:     HashMap::new(),
            body_text:   r#"{"key":"val"}"#.into(),
            body_json:   Some(serde_json::json!({"key": "val"})),
        });
        let raw = mock.request("GET", "/redfish/v1", HashMap::new(), None).await.unwrap();
        assert_eq!(raw.body_text, r#"{"key":"val"}"#);
    }
}
