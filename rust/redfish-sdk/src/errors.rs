use thiserror::Error;

/// All SDK-level errors.
#[derive(Debug, Error)]
pub enum RedfishError {
    #[error("Connection failed: {0}")]
    ConnectionFailed(String),

    #[error("TLS error: {0}")]
    TlsError(String),

    #[error("Authentication failed: {0}")]
    AuthFailed(String),

    #[error("Protocol error: {0}")]
    ProtocolError(String),

    #[error("HTTP error {status_code}: {message}")]
    HttpError { status_code: u16, message: String },

    #[error("Task timed out")]
    Timeout,

    #[error("Task failed: {0}")]
    TaskFailed(String),

    #[error("JSON parse error: {0}")]
    ParseError(String),

    #[error("IO error: {0}")]
    IoError(String),
}

impl From<reqwest::Error> for RedfishError {
    fn from(e: reqwest::Error) -> Self {
        if e.is_connect() || e.is_timeout() {
            RedfishError::ConnectionFailed(e.to_string())
        } else {
            RedfishError::HttpError {
                status_code: e.status().map(|s| s.as_u16()).unwrap_or(0),
                message:     e.to_string(),
            }
        }
    }
}

impl From<serde_json::Error> for RedfishError {
    fn from(e: serde_json::Error) -> Self {
        RedfishError::ParseError(e.to_string())
    }
}
