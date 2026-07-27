mod routes;
mod server;

use clap::Parser;
use tracing_subscriber::EnvFilter;

#[derive(Parser)]
#[command(name = "opsd", about = "Credential store HTTP daemon")]
struct Args {
    #[arg(long, default_value = "127.0.0.1:9470")]
    listen: String,

    #[arg(long, env = "KSEAL_CONFIG", default_value = "/app/config/service.toml")]
    config: String,
}

#[tokio::main]
async fn main() {
    tracing_subscriber::fmt()
        .with_env_filter(EnvFilter::from_default_env())
        .init();

    let args = Args::parse();
    let config = server::load_config(&args.config);
    server::run(&args.listen, config).await;
}
