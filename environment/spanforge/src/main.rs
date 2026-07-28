mod cli {
    pub mod arguments;
    pub mod dispatch;
}
mod decoy {
    pub mod spectrum;
}
mod diagnostic {
    pub mod failure;
}
mod input {
    pub mod canonicalize;
    pub mod model_schema;
    pub mod plan_schema;
    pub mod strict_json;
    pub mod survey_schema;
}
mod linalg {
    pub mod cholesky;
    pub mod dense;
    pub mod generalized;
    pub mod jacobi;
    pub mod orthogonalize;
}
mod modal {
    pub mod cluster;
    pub mod mass_normalize;
    pub mod pairing;
    pub mod sensor_projection;
    pub mod subspace_mac;
}
mod model {
    pub mod assembly;
    pub mod physicality;
}
mod objective {
    pub mod evaluate;
    pub mod regularization;
    pub mod residuals;
}
mod optimize {
    pub mod bounds;
    pub mod finite_difference;
    pub mod termination;
    pub mod trust_region;
}
mod report {
    pub mod calibration_record;
    pub mod canonical_writer;
    pub mod publication;
}
mod sensitivity {
    pub mod confidence;
    pub mod jacobian;
    pub mod rank;
}

use cli::arguments::parse;
use cli::dispatch::run_or_exit;

fn main() {
    let args: Vec<String> = std::env::args().collect();
    match parse(&args) {
        Ok(cmd) => run_or_exit(cmd),
        Err((code, msg)) => diagnostic::failure::emit_and_exit(code, &msg),
    }
}
