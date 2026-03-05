use crate::context::ClientContext;
use crate::errors::RedfishError;
use crate::protocol::response::RedfishResponse;
use futures::{Stream, StreamExt};
use std::pin::Pin;

/// OData query parameters for log entry requests.
#[derive(Debug, Default, Clone)]
pub struct LogQuery {
    pub top:          Option<usize>,
    pub skip:         Option<usize>,
    pub severity:     Option<String>,
    pub message_id:   Option<String>,
    pub odata_filter: Option<String>,
}

/// A parsed IPMI SEL entry — structured or flat "Raw data: xx xx …" format.
#[derive(Debug, Clone)]
pub struct SelEntry {
    pub timestamp:  Option<String>,
    pub message_id: Option<String>,
    pub severity:   Option<String>,
    pub message:    Option<String>,
    pub raw_bytes:  Option<Vec<u8>>,
}

pub struct LogServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> LogServiceHandle<'ctx> {
    pub(crate) fn new(ctx: &'ctx ClientContext) -> Self { Self { ctx } }

    fn service_base(&self) -> String {
        self.ctx.base_path.clone()
    }

    // ── Async ────────────────────────────────────────────────────────────────

    /// List all log services from Systems/1 and Managers collections.
    pub async fn list_services(&self) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/Systems/1/LogServices", self.service_base());
        self.ctx.get(&uri).await
    }

    /// Fetch one page of log entries with optional OData query.
    pub async fn list_entries(
        &self,
        log_service_uri: &str,
        query:           LogQuery,
    ) -> Result<RedfishResponse, RedfishError> {
        let entries_uri = format!("{}/Entries{}", log_service_uri, build_query_string(&query));
        self.ctx.get(&entries_uri).await
    }

    /// Auto-paginating stream — follows Members@odata.nextLink across pages.
    pub fn iter_entries(
        &self,
        log_service_uri: &str,
        query:           LogQuery,
        max_pages:       Option<usize>,
    ) -> Pin<Box<dyn Stream<Item = Result<RedfishResponse, RedfishError>> + Send + '_>> {
        let first_uri = format!("{}/Entries{}", log_service_uri, build_query_string(&query));

        Box::pin(async_stream::try_stream! {
            let mut next: Option<String> = Some(first_uri);
            let mut pages = 0usize;
            let limit = max_pages.unwrap_or(usize::MAX);

            while let Some(uri) = next.take() {
                if pages >= limit { break; }
                let resp = self.ctx.get(&uri).await?;
                next = resp.body.as_ref()
                    .and_then(|b| b.get("Members@odata.nextLink"))
                    .and_then(|v| v.as_str())
                    .map(String::from);
                pages += 1;
                yield resp;
            }
        })
    }

    pub async fn get_entry(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(uri).await
    }

    pub async fn clear_log(&self, log_service_uri: &str) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/Actions/LogService.ClearLog", log_service_uri);
        self.ctx.post(&uri, serde_json::json!({})).await
    }

    /// Parse a raw IPMI SEL entry — structured JSON or flat "Raw data: xx xx …" string.
    pub fn parse_sel_entry(entry: &serde_json::Value) -> Option<SelEntry> {
        let message = entry.get("Message").and_then(|v| v.as_str()).unwrap_or("");

        let raw_bytes = if message.starts_with("Raw data:") || message.starts_with("Raw Data:") {
            let hex_part = message.splitn(2, ':').nth(1).unwrap_or("").trim();
            let bytes: Vec<u8> = hex_part
                .split_whitespace()
                .filter_map(|h| u8::from_str_radix(h, 16).ok())
                .collect();
            if bytes.is_empty() { None } else { Some(bytes) }
        } else {
            None
        };

        Some(SelEntry {
            timestamp:  entry.get("Created").and_then(|v| v.as_str()).map(String::from),
            message_id: entry.get("MessageId").and_then(|v| v.as_str()).map(String::from),
            severity:   entry.get("Severity").and_then(|v| v.as_str()).map(String::from),
            message:    if raw_bytes.is_some() { None } else { Some(message.to_string()) },
            raw_bytes,
        })
    }

    // ── Blocking wrappers ────────────────────────────────────────────────────

    pub fn list_services_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_services())
    }

    pub fn list_entries_blocking(&self, uri: &str, query: LogQuery) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_entries(uri, query))
    }

    pub fn iter_entries_blocking<F>(
        &self,
        log_service_uri: &str,
        query:           LogQuery,
        max_pages:       Option<usize>,
        mut on_page:     F,
    ) where F: FnMut(RedfishResponse) -> bool {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(async {
            let mut stream = self.iter_entries(log_service_uri, query, max_pages);
            while let Some(result) = stream.next().await {
                match result {
                    Ok(page) => { if !on_page(page) { break; } }
                    Err(e)   => { tracing::error!("iter_entries error: {}", e); break; }
                }
            }
        });
    }

    pub fn get_entry_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_entry(uri))
    }

    pub fn clear_log_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.clear_log(uri))
    }
}

// ── OData query string builder ────────────────────────────────────────────────
// Order required by OpenBMC: $skip → $top → $filter

fn build_query_string(q: &LogQuery) -> String {
    let mut parts: Vec<String> = Vec::new();

    if let Some(skip) = q.skip { parts.push(format!("$skip={skip}")); }
    if let Some(top)  = q.top  { parts.push(format!("$top={top}")); }

    // odata_filter overrides severity / message_id
    if let Some(ref f) = q.odata_filter {
        parts.push(format!("$filter={}", urlencoding::encode(f)));
    } else {
        let filter = match (&q.severity, &q.message_id) {
            (Some(s), None)    => Some(format!("Severity eq '{s}'")),
            (None,    Some(m)) => Some(format!("MessageId eq '{m}'")),
            (Some(s), Some(m)) => Some(format!("Severity eq '{s}' and MessageId eq '{m}'")),
            _                  => None,
        };
        if let Some(f) = filter {
            parts.push(format!("$filter={}", urlencoding::encode(&f)));
        }
    }

    if parts.is_empty() { String::new() } else { format!("?{}", parts.join("&")) }
}

// ── Unit tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn structured_entry_all_fields() {
        let entry = serde_json::json!({
            "Created":   "2024-01-15T10:00:00Z",
            "MessageId": "IPMI.1.0.SELEntryAdded",
            "Severity":  "Critical",
            "Message":   "Temperature sensor exceeded threshold."
        });
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert_eq!(sel.timestamp.as_deref(),  Some("2024-01-15T10:00:00Z"));
        assert_eq!(sel.message_id.as_deref(), Some("IPMI.1.0.SELEntryAdded"));
        assert_eq!(sel.severity.as_deref(),   Some("Critical"));
        assert_eq!(sel.message.as_deref(),
                   Some("Temperature sensor exceeded threshold."));
        assert!(sel.raw_bytes.is_none());
    }

    #[test]
    fn raw_data_lowercase_prefix_parsed() {
        let entry = serde_json::json!({"Message": "Raw data: 0A 1B 2C 3D"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert_eq!(sel.raw_bytes.as_deref(), Some(vec![0x0A, 0x1B, 0x2C, 0x3D].as_slice()));
        assert!(sel.message.is_none(), "message must be None when raw_bytes present");
    }

    #[test]
    fn raw_data_titlecase_prefix_parsed() {
        let entry = serde_json::json!({"Message": "Raw Data: FF 00 AB"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert_eq!(sel.raw_bytes.as_deref(), Some(vec![0xFF, 0x00, 0xAB].as_slice()));
    }

    #[test]
    fn raw_data_single_byte() {
        let entry = serde_json::json!({"Message": "Raw data: DE"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert_eq!(sel.raw_bytes.as_deref(), Some(vec![0xDE].as_slice()));
    }

    #[test]
    fn raw_data_invalid_hex_tokens_skipped() {
        // "ZZ" is invalid hex — only the valid bytes 0x1B and 0x2C survive
        let entry = serde_json::json!({"Message": "Raw data: ZZ 1B 2C"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert_eq!(sel.raw_bytes.as_deref(), Some(vec![0x1B, 0x2C].as_slice()));
    }

    #[test]
    fn raw_data_all_invalid_hex_gives_none_bytes() {
        // All tokens invalid → bytes vec is empty → raw_bytes = None
        // message is then Some because raw_bytes is None
        let entry = serde_json::json!({"Message": "Raw data: ZZ WW"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert!(sel.raw_bytes.is_none());
        assert!(sel.message.is_some());
    }

    #[test]
    fn empty_entry_returns_some_with_all_fields_none() {
        let entry = serde_json::json!({});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert!(sel.timestamp.is_none());
        assert!(sel.message_id.is_none());
        assert!(sel.severity.is_none());
        assert!(sel.raw_bytes.is_none());
    }

    #[test]
    fn missing_severity_is_none() {
        let entry = serde_json::json!({"MessageId": "X.1.0.Foo", "Message": "msg"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert!(sel.severity.is_none());
    }

    #[test]
    fn missing_created_timestamp_is_none() {
        let entry = serde_json::json!({"Message": "some message"});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert!(sel.timestamp.is_none());
    }

    #[test]
    fn structured_message_not_nil_when_no_raw_bytes() {
        let entry = serde_json::json!({"Message": "Fan speed warning."});
        let sel = LogServiceHandle::parse_sel_entry(&entry).unwrap();
        assert_eq!(sel.message.as_deref(), Some("Fan speed warning."));
        assert!(sel.raw_bytes.is_none());
    }
}
