use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError, RedfishResponse};
use serde_json::json;

fn dump(label: &str, resp: &RedfishResponse) {
    let icon = if resp.success { "OK" } else { "FAIL" };
    println!("\n[{}] [{}] {label}", resp.status_code, icon);
    if let Some(b) = &resp.body {
        let keys: Vec<&str> = b.as_object().map(|o| o.keys()
            .filter(|k| !k.starts_with('@')).take(10)
            .map(|s| s.as_str()).collect()).unwrap_or_default();
        println!("   body keys : {keys:?}");
    }
    for msg in &resp.extended_info {
        println!("   message   : [{}] {}", msg.severity, msg.message);
    }
}

fn parse_args() -> (String, u16, String, String, bool) {
    let mut host = "127.0.0.1".to_string();
    let mut port = 8000u16;
    let mut user = "admin".to_string();
    let mut password = "password".to_string();
    let mut no_tls = false;
    let mut it = std::env::args().skip(1);
    while let Some(a) = it.next() {
        match a.as_str() {
            "--host"          => { host = it.next().unwrap(); }
            "--port"          => { port = it.next().unwrap().parse().unwrap(); }
            "--user"          => { user = it.next().unwrap(); }
            "--password"      => { password = it.next().unwrap(); }
            "--no-tls-verify" => { no_tls = true; }
            _ => {}
        }
    }
    (host, port, user, password, no_tls)
}


#[tokio::main]
async fn main() -> Result<(), RedfishError> {
    tracing_subscriber::fmt::init();
    let (host, port, user, password, no_tls) = parse_args();
    let ctx = connect(&host, port, Credentials::new(&user, &password),
        AuthMode::Session, ConnectionConfig { verify_tls: !no_tls, ..Default::default() }).await?;

    let root = ctx.get("/redfish/v1").await?;
    dump("GET /redfish/v1", &root);
    if root.success {
        if let Some(b) = &root.body {
            println!("   RedfishVersion : {}", b["RedfishVersion"].as_str().unwrap_or("?"));
            println!("   UUID           : {}", b["UUID"].as_str().unwrap_or("?"));
        }
    }

    let missing = ctx.get("/redfish/v1/DoesNotExist").await?;
    dump("GET /redfish/v1/DoesNotExist (expect 404)", &missing);

    let systems = ctx.get("/redfish/v1/Systems").await?;
    dump("GET /redfish/v1/Systems", &systems);

    let first_sys: Option<String> = systems.body.as_ref()
        .and_then(|b| b["Members"].as_array())
        .and_then(|a| a.first())
        .and_then(|m| m["@odata.id"].as_str())
        .map(str::to_string);

    if let Some(ref uri) = first_sys {
        let pr = ctx.patch(uri, json!({"AssetTag": "RSDK-Sample-04"})).await?;
        dump(&format!("PATCH {uri}"), &pr);
        let vr = ctx.get(uri).await?;
        dump(&format!("GET {uri} (verify)"), &vr);
        if let Some(b) = &vr.body {
            println!("   AssetTag : {}", b["AssetTag"].as_str().unwrap_or("?"));
        }
        let reset_uri = format!("{uri}/Actions/ComputerSystem.Reset");
        let rr = ctx.post(&reset_uri, json!({"ResetType":"GracefulRestart"})).await?;
        dump(&format!("POST {reset_uri}"), &rr);
        if let Some(task) = &rr.task {
            println!("   Task URI : {}", task.task_uri);
        }
    }

    println!("\nDirect API sample complete");
    Ok(())
}
