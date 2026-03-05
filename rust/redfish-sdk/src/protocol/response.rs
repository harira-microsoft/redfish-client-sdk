use std::collections::HashMap;
use crate::transport::types::RawHttpResponse;

/// A decoded Redfish extended message.
#[derive(Debug, Clone)]
pub struct RedfishMessage {
    pub message_id:   String,
    pub message:      String,
    pub severity:     String,
    pub resolution:   Option<String>,
    pub message_args: Vec<String>,
}

/// Unified response returned by every SDK method.
#[derive(Debug)]
pub struct RedfishResponse {
    pub status_code:   u16,
    pub success:       bool,
    pub headers:       HashMap<String, String>,
    pub body:          Option<serde_json::Value>,
    pub extended_info: Vec<RedfishMessage>,
    pub task:          Option<crate::protocol::task::RedfishTask>,
    pub raw:           String,
}

impl RedfishResponse {
    /// Build from a RawHttpResponse. A 202 response populates `task`.
    pub(crate) fn from_raw(raw: RawHttpResponse) -> Self {
        let success = (200..300).contains(&raw.status_code);
        let extended_info = parse_extended_info(raw.body_json.as_ref());

        // On 202 extract the task URI from the Location header.
        let task = if raw.status_code == 202 {
            raw.headers
                .get("location")
                .or_else(|| raw.headers.get("Location"))
                .map(|uri| crate::protocol::task::RedfishTask::pending(uri))
        } else {
            None
        };

        Self {
            status_code:   raw.status_code,
            success,
            headers:       raw.headers,
            body:          raw.body_json,
            extended_info,
            task,
            raw:           raw.body_text,
        }
    }
}

fn parse_extended_info(body: Option<&serde_json::Value>) -> Vec<RedfishMessage> {
    let Some(body) = body else { return vec![] };

    // Look in body["error"]["@Message.ExtendedInfo"] or body["@Message.ExtendedInfo"]
    let arr = body
        .get("error")
        .and_then(|e| e.get("@Message.ExtendedInfo"))
        .or_else(|| body.get("@Message.ExtendedInfo"))
        .and_then(|v| v.as_array());

    let Some(arr) = arr else { return vec![] };

    arr.iter().filter_map(|item| {
        Some(RedfishMessage {
            message_id:   item["MessageId"].as_str()?.to_string(),
            message:      item.get("Message").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            severity:     item.get("Severity").and_then(|v| v.as_str()).unwrap_or("").to_string(),
            resolution:   item.get("Resolution").and_then(|v| v.as_str()).map(String::from),
            message_args: item.get("MessageArgs")
                .and_then(|v| v.as_array())
                .map(|a| a.iter().filter_map(|s| s.as_str().map(String::from)).collect())
                .unwrap_or_default(),
        })
    }).collect()
}

// ── Unit tests ───────────────────────────────────────────────────────────────

#[cfg(test)]
mod tests {
    use super::*;
    use crate::transport::types::RawHttpResponse;

    fn raw(status: u16, body: Option<serde_json::Value>) -> RawHttpResponse {
        RawHttpResponse {
            status_code: status,
            headers:     HashMap::new(),
            body_text:   String::new(),
            body_json:   body,
        }
    }

    fn raw_with_header(status: u16, key: &str, val: &str) -> RawHttpResponse {
        let mut headers = HashMap::new();
        headers.insert(key.to_string(), val.to_string());
        RawHttpResponse { status_code: status, headers,
                          body_text: String::new(), body_json: None }
    }

    // ── success flag ─────────────────────────────────────────────────────────

    #[test] fn success_200() { assert!( RedfishResponse::from_raw(raw(200, None)).success); }
    #[test] fn success_201() { assert!( RedfishResponse::from_raw(raw(201, None)).success); }
    #[test] fn success_204() { assert!( RedfishResponse::from_raw(raw(204, None)).success); }
    #[test] fn success_299() { assert!( RedfishResponse::from_raw(raw(299, None)).success); }
    #[test] fn fail_300()    { assert!(!RedfishResponse::from_raw(raw(300, None)).success); }
    #[test] fn fail_400()    { assert!(!RedfishResponse::from_raw(raw(400, None)).success); }
    #[test] fn fail_401()    { assert!(!RedfishResponse::from_raw(raw(401, None)).success); }
    #[test] fn fail_404()    { assert!(!RedfishResponse::from_raw(raw(404, None)).success); }
    #[test] fn fail_500()    { assert!(!RedfishResponse::from_raw(raw(500, None)).success); }

    // ── body / status ────────────────────────────────────────────────────────

    #[test]
    fn body_propagated() {
        let body = serde_json::json!({"@odata.id": "/redfish/v1"});
        let resp = RedfishResponse::from_raw(raw(200, Some(body)));
        assert_eq!(resp.body.unwrap()["@odata.id"], "/redfish/v1");
    }

    #[test]
    fn no_body_is_none() {
        assert!(RedfishResponse::from_raw(raw(204, None)).body.is_none());
    }

    #[test]
    fn status_code_preserved() {
        assert_eq!(RedfishResponse::from_raw(raw(418, None)).status_code, 418);
    }

    // ── task ─────────────────────────────────────────────────────────────────

    #[test]
    fn task_from_202_lowercase_location() {
        let resp = RedfishResponse::from_raw(
            raw_with_header(202, "location", "/redfish/v1/TaskService/Tasks/1"));
        let task = resp.task.expect("task should be Some on 202");
        assert_eq!(task.task_uri, "/redfish/v1/TaskService/Tasks/1");
        assert_eq!(task.task_id,  "1");
        assert_eq!(task.state,    "Running");
    }

    #[test]
    fn task_from_202_mixed_case_location() {
        let resp = RedfishResponse::from_raw(
            raw_with_header(202, "Location", "/redfish/v1/TaskService/Tasks/99"));
        assert!(resp.task.is_some());
    }

    #[test]
    fn no_task_on_200_even_with_location_header() {
        let resp = RedfishResponse::from_raw(
            raw_with_header(200, "location", "/redfish/v1/TaskService/Tasks/1"));
        assert!(resp.task.is_none());
    }

    #[test]
    fn no_task_on_201() {
        assert!(RedfishResponse::from_raw(raw(201, None)).task.is_none());
    }

    #[test]
    fn no_task_on_202_without_location() {
        assert!(RedfishResponse::from_raw(raw(202, None)).task.is_none());
    }

    // ── extended_info ────────────────────────────────────────────────────────

    #[test]
    fn extended_info_top_level() {
        let body = serde_json::json!({
            "@Message.ExtendedInfo": [{
                "MessageId": "Base.1.0.Success",
                "Message":   "Completed successfully.",
                "Severity":  "OK"
            }]
        });
        let resp = RedfishResponse::from_raw(raw(200, Some(body)));
        assert_eq!(resp.extended_info.len(), 1);
        assert_eq!(resp.extended_info[0].message_id, "Base.1.0.Success");
        assert_eq!(resp.extended_info[0].severity,   "OK");
    }

    #[test]
    fn extended_info_in_error_wrapper() {
        let body = serde_json::json!({
            "error": {
                "code": "Base.1.0.GeneralError",
                "@Message.ExtendedInfo": [{
                    "MessageId": "Base.1.0.GeneralError",
                    "Message":   "A general error has occurred.",
                    "Severity":  "Critical"
                }]
            }
        });
        let resp = RedfishResponse::from_raw(raw(400, Some(body)));
        assert_eq!(resp.extended_info.len(), 1);
        assert_eq!(resp.extended_info[0].message_id, "Base.1.0.GeneralError");
        assert_eq!(resp.extended_info[0].severity,   "Critical");
    }

    #[test]
    fn extended_info_multiple_entries() {
        let body = serde_json::json!({
            "@Message.ExtendedInfo": [
                {"MessageId": "A.1.0.Foo", "Message": "First",  "Severity": "OK"},
                {"MessageId": "A.1.0.Bar", "Message": "Second", "Severity": "Warning"}
            ]
        });
        let resp = RedfishResponse::from_raw(raw(200, Some(body)));
        assert_eq!(resp.extended_info.len(), 2);
        assert_eq!(resp.extended_info[1].severity, "Warning");
    }

    #[test]
    fn extended_info_empty_on_no_body() {
        assert!(RedfishResponse::from_raw(raw(404, None)).extended_info.is_empty());
    }

    #[test]
    fn extended_info_item_without_message_id_skipped() {
        let body = serde_json::json!({
            "@Message.ExtendedInfo": [
                {"Message": "no id here", "Severity": "OK"},
                {"MessageId": "Base.1.0.OK", "Message": "has id", "Severity": "OK"}
            ]
        });
        let resp = RedfishResponse::from_raw(raw(200, Some(body)));
        assert_eq!(resp.extended_info.len(), 1);
        assert_eq!(resp.extended_info[0].message_id, "Base.1.0.OK");
    }

    #[test]
    fn extended_info_message_args_parsed() {
        let body = serde_json::json!({
            "@Message.ExtendedInfo": [{
                "MessageId":   "Base.1.0.PropertyNotWritable",
                "Message":     "The property Id is a read-only property.",
                "Severity":    "Warning",
                "MessageArgs": ["Id"]
            }]
        });
        let resp = RedfishResponse::from_raw(raw(400, Some(body)));
        assert_eq!(resp.extended_info[0].message_args, vec!["Id"]);
    }

    #[test]
    fn extended_info_resolution_parsed() {
        let body = serde_json::json!({
            "@Message.ExtendedInfo": [{
                "MessageId":  "Base.1.0.GeneralError",
                "Message":    "Error.",
                "Severity":   "Critical",
                "Resolution": "Check logs."
            }]
        });
        let resp = RedfishResponse::from_raw(raw(500, Some(body)));
        assert_eq!(resp.extended_info[0].resolution.as_deref(), Some("Check logs."));
    }

    #[test]
    fn headers_propagated() {
        let mut hdrs = HashMap::new();
        hdrs.insert("content-type".into(), "application/json".into());
        let raw_resp = RawHttpResponse {
            status_code: 200, headers: hdrs,
            body_text: String::new(), body_json: None,
        };
        let resp = RedfishResponse::from_raw(raw_resp);
        assert_eq!(resp.headers.get("content-type").map(String::as_str),
                   Some("application/json"));
    }
}
