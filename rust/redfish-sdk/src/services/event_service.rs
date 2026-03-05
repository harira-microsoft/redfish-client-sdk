use crate::context::ClientContext;
use crate::errors::RedfishError;
use crate::protocol::response::RedfishResponse;

/// Handle for EventService operations.
pub struct EventServiceHandle<'ctx> {
    ctx: &'ctx ClientContext,
}

impl<'ctx> EventServiceHandle<'ctx> {
    pub(crate) fn new(ctx: &'ctx ClientContext) -> Self { Self { ctx } }

    fn service_uri(&self) -> String {
        self.ctx.resolve_service_uri("EventService", "/EventService")
    }

    // ── Async ────────────────────────────────────────────────────────────────

    pub async fn get_service_info(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(&self.service_uri()).await
    }

    pub async fn subscribe(
        &self,
        destination:       &str,
        event_types:       Vec<String>,
        registry_prefixes: Vec<String>,
        message_ids:       Vec<String>,
        resource_types:    Vec<String>,
        event_format_type: Option<&str>,
        context:           Option<&str>,
        protocol:          &str,
        subscription_type: &str,
    ) -> Result<RedfishResponse, RedfishError> {
        let subs_uri = format!("{}/Subscriptions", self.service_uri());
        let mut body = serde_json::json!({
            "Destination":       destination,
            "EventTypes":        event_types,
            "RegistryPrefixes":  registry_prefixes,
            "MessageIds":        message_ids,
            "Protocol":          protocol,
            "SubscriptionType":  subscription_type,
        });

        if !resource_types.is_empty() {
            body["ResourceTypes"] = serde_json::json!(resource_types);
        }
        if let Some(fmt) = event_format_type {
            body["EventFormatType"] = serde_json::json!(fmt);
        }
        if let Some(ctx_str) = context {
            body["Context"] = serde_json::json!(ctx_str);
        }

        self.ctx.post(&subs_uri, body).await
    }

    pub async fn list_subscriptions(&self) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/Subscriptions", self.service_uri());
        self.ctx.get(&uri).await
    }

    pub async fn get_subscription(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.get(uri).await
    }

    pub async fn delete_subscription(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.del(uri).await
    }

    pub async fn submit_test_event(&self, event_data: serde_json::Value) -> Result<RedfishResponse, RedfishError> {
        let uri = format!("{}/Actions/EventService.SubmitTestEvent", self.service_uri());
        self.ctx.post(&uri, event_data).await
    }

    // ── Blocking wrappers ────────────────────────────────────────────────────

    pub fn get_service_info_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_service_info())
    }

    pub fn subscribe_blocking(
        &self,
        destination: &str, event_types: Vec<String>, registry_prefixes: Vec<String>,
        message_ids: Vec<String>, resource_types: Vec<String>,
        event_format_type: Option<&str>, context: Option<&str>,
        protocol: &str, subscription_type: &str,
    ) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.subscribe(
            destination, event_types, registry_prefixes, message_ids,
            resource_types, event_format_type, context, protocol, subscription_type,
        ))
    }

    pub fn list_subscriptions_blocking(&self) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.list_subscriptions())
    }

    pub fn get_subscription_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.get_subscription(uri))
    }

    pub fn delete_subscription_blocking(&self, uri: &str) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.delete_subscription(uri))
    }

    pub fn submit_test_event_blocking(&self, data: serde_json::Value) -> Result<RedfishResponse, RedfishError> {
        self.ctx.runtime.as_ref().expect("no runtime").block_on(self.submit_test_event(data))
    }
}
