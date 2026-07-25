//! Stable public failure diagnostics for modal reconciliation.

use serde::Serialize;
use std::io::{self, Write};
use std::process;

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum FailureCode {
    EPath,
    EModelSchema,
    EMatrixSymmetry,
    EMassPhysicality,
    EStiffnessBox,
    EEigensystem,
    ESurveySchema,
    EPlanSchema,
    EModalPairing,
    EOptimization,
    ESensitivity,
    EReport,
}

impl FailureCode {
    pub fn as_str(self) -> &'static str {
        match self {
            FailureCode::EPath => "E_PATH",
            FailureCode::EModelSchema => "E_MODEL_SCHEMA",
            FailureCode::EMatrixSymmetry => "E_MATRIX_SYMMETRY",
            FailureCode::EMassPhysicality => "E_MASS_PHYSICALITY",
            FailureCode::EStiffnessBox => "E_STIFFNESS_BOX",
            FailureCode::EEigensystem => "E_EIGENSYSTEM",
            FailureCode::ESurveySchema => "E_SURVEY_SCHEMA",
            FailureCode::EPlanSchema => "E_PLAN_SCHEMA",
            FailureCode::EModalPairing => "E_MODAL_PAIRING",
            FailureCode::EOptimization => "E_OPTIMIZATION",
            FailureCode::ESensitivity => "E_SENSITIVITY",
            FailureCode::EReport => "E_REPORT",
        }
    }
}

#[derive(Serialize)]
struct DiagnosticLine<'a> {
    code: &'a str,
    message: &'a str,
}

pub fn emit_and_exit(code: FailureCode, message: &str) -> ! {
    let line = DiagnosticLine {
        code: code.as_str(),
        message,
    };
    let payload = serde_json::to_string(&line).unwrap_or_else(|_| {
        format!(
            "{{\"code\":\"{}\",\"message\":\"diagnostic serialization failure\"}}",
            code.as_str()
        )
    });
    let mut err = io::stderr();
    let _ = writeln!(err, "{}", payload);
    let _ = err.flush();
    process::exit(1);
}

pub type AppResult<T> = Result<T, (FailureCode, String)>;

pub fn fail<T>(code: FailureCode, message: impl Into<String>) -> AppResult<T> {
    Err((code, message.into()))
}
