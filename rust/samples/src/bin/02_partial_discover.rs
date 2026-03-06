use redfish_sdk::{connect, AuthMode, ConnectionConfig, Credentials, RedfishError};

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
    let no_tls_proto = std::env::args().any(|a| a == "--no-tls");
    let creds = Credentials::new(&user, &password);
    let config = ConnectionConfig { verify_tls: !no_tls, use_tls: !no_tls_proto, ..Default::default() };
    let ctx = connect(&host, port, creds, AuthMode::Session, config).await?;

    println!("Partial discovery - Systems only ...");
    let result = ctx.discovery().partial("Systems").await?;
    match result.service_uri("Systems") {
        Some(uri) => println!("  Systems URI: {uri}"),
        None      => println!("  Systems not found"),
    }

    println!("
Partial discovery - EventService only ...");
    let result2 = ctx.discovery().partial("EventService").await?;
    match result2.service_uri("EventService") {
        Some(uri) => println!("  EventService URI: {uri}"),
        None      => println!("  EventService not available"),
    }

    println!("
Fetching root info ...");
    let _ = ctx.discovery().root().await?;
    let caps = ctx.capabilities();
    println!("  Redfish version : {}", caps.redfish_version);

    println!("
Partial discovery complete");
    Ok(())
}
