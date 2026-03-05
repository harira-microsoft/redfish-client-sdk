use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError, RedfishTask};
use serde_json::json;

fn parse_args() -> (String, u16, String, String, bool, f64) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut timeout = 60.0f64;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--host"          => { host = it.next().unwrap(); }
            "--port"          => { port = it.next().unwrap().parse().unwrap(); }
            "--user"          => { user = it.next().unwrap(); }
            "--password"      => { password = it.next().unwrap(); }
            "--no-tls-verify" => { no_tls = true; }
            "--timeout"       => { timeout = it.next().unwrap().parse().unwrap(); }
            _ => {}
        }
    }
    (host, port, user, password, no_tls, timeout)
}

async fn trigger_task(ctx: &redfish_sdk::ClientContext) -> Option<RedfishTask> {
    let systems = ctx.get("/redfish/v1/Systems").await.ok()?;
    let sys_uri = systems.body.as_ref()
        .and_then(|b| b["Members"].as_array())
        .and_then(|a| a.first())
        .and_then(|m| m["@odata.id"].as_str())?.to_string();
    let reset_uri = format!("{sys_uri}/Actions/ComputerSystem.Reset");
    for rt in &["GracefulRestart", "ForceRestart"] {
        let resp = ctx.post(&reset_uri, json!({"ResetType": rt})).await.ok()?;
        if let Some(task) = resp.task { return Some(task); }
    }
    None
}

#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls, timeout_secs) = parse_args();
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, ..Default::default() }).await?;

    println!("Attempting to trigger a task ...");
    let task = match trigger_task(&ctx).await {
        Some(t) => t,
        None => {
            println!("  No task returned");
            let tr = ctx.get("/redfish/v1/TaskService/Tasks").await?;
            if tr.success {
                let n = tr.body.as_ref().and_then(|b| b["Members"].as_array()).map(|a| a.len()).unwrap_or(0);
                println!("  Existing tasks: {n}");
            }
            println!("\nTask polling sample complete (no live task)");
            return Ok(());
        }
    };

    println!("  Task URI: {}", task.task_uri);
    println!("  Initial state: {}", task.state);

    println!("\n-- Polling (2s interval, max {}s) --", (timeout_secs / 2.0) as u32);
    let mut state = task.state.clone();
    let deadline = std::time::Instant::now() + std::time::Duration::from_secs_f64(timeout_secs / 2.0);
    loop {
        if std::time::Instant::now() >= deadline { println!("  Timeout"); break; }
        tokio::time::sleep(std::time::Duration::from_secs(2)).await;
        let pr = ctx.get(&task.task_uri).await?;
        if let Some(b) = &pr.body {
            if let Some(s) = b["TaskState"].as_str() { state = s.to_string(); }
            if let Some(p) = b["PercentComplete"].as_u64() { println!("  pct={p}%"); }
        }
        println!("  state={state}");
        match state.as_str() {
            "Completed" | "Killed" | "Exception" | "Cancelled" => break,
            _ => {}
        }
    }
    println!("  Final state: {state}");

    println!("\nTask polling sample complete");
    Ok(())
}
