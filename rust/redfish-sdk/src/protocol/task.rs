use crate::errors::RedfishError;
use crate::protocol::response::RedfishResponse;
use std::time::{Duration, Instant};

/// Terminal states — polling stops when any of these is reached.
const TERMINAL_STATES: &[&str] = &[
    "Completed", "Killed", "Exception", "Cancelled",
];

/// Publicly visible task handle returned inside a 202 RedfishResponse.
#[derive(Debug)]
pub struct RedfishTask {
    pub task_uri:         String,
    pub task_id:          String,
    pub state:            String,
    pub percent_complete: Option<u8>,
    pub messages:         Vec<crate::protocol::response::RedfishMessage>,
}

impl RedfishTask {
    /// Create a bare pending task from a Location URI.
    pub(crate) fn pending(uri: &str) -> Self {
        let id = uri.split('/').next_back().unwrap_or("").to_string();
        Self {
            task_uri:         uri.to_string(),
            task_id:          id,
            state:            "Running".to_string(),
            percent_complete: None,
            messages:         vec![],
        }
    }

    /// Poll until terminal state or timeout.
    ///
    /// `http_fn` is an async closure that takes a URI and returns a RedfishResponse.
    /// This pattern avoids holding a reference to ClientContext inside the task struct.
    pub async fn wait<F, Fut>(
        &mut self,
        poll_interval_secs: f32,
        timeout_secs:       f32,
        http_fn:            F,
    ) -> Result<RedfishResponse, RedfishError>
    where
        F:   Fn(String) -> Fut,
        Fut: std::future::Future<Output = Result<RedfishResponse, RedfishError>>,
    {
        let deadline = Instant::now() + Duration::from_secs_f32(timeout_secs);
        let poll     = Duration::from_secs_f32(poll_interval_secs);

        loop {
            if Instant::now() >= deadline {
                return Err(RedfishError::Timeout);
            }

            tokio::time::sleep(poll).await;

            let resp = http_fn(self.task_uri.clone()).await?;

            if let Some(ref body) = resp.body {
                if let Some(state) = body.get("TaskState").and_then(|v| v.as_str()) {
                    self.state = state.to_string();
                }
                if let Some(pct) = body.get("PercentComplete").and_then(|v| v.as_u64()) {
                    self.percent_complete = Some(pct as u8);
                }
            }

            tracing::debug!("Task {} — state={} pct={:?}", self.task_id, self.state, self.percent_complete);

            if TERMINAL_STATES.contains(&self.state.as_str()) {
                if self.state == "Completed" {
                    return Ok(resp);
                } else {
                    return Err(RedfishError::TaskFailed(format!(
                        "Task {} ended in state {}", self.task_id, self.state
                    )));
                }
            }
        }
    }
}
