//! Dispatch spectrum and calibrate workflows.

use crate::cli::arguments::{print_help, Command};
use crate::decoy::spectrum::run_spectrum;
use crate::diagnostic::failure::{emit_and_exit, fail, AppResult, FailureCode};
use crate::input::model_schema::load_model;
use crate::input::plan_schema::load_plan;
use crate::input::survey_schema::load_survey;
use crate::model::physicality::{validate_mass, validate_stiffness_box};
use crate::optimize::trust_region::calibrate_parameters;
use std::path::Path;

pub fn dispatch(cmd: Command) -> AppResult<()> {
    match cmd {
        Command::Help => {
            print_help();
            Ok(())
        }
        Command::Spectrum { model } => run_spectrum(&model),
        Command::Calibrate {
            model,
            survey,
            plan,
            report: _,
        } => run_calibrate_starter(&model, &survey, &plan),
    }
}

fn run_calibrate_starter(
    model_path: &Path,
    survey_path: &Path,
    plan_path: &Path,
) -> AppResult<()> {
    let model = load_model(model_path)?;
    let m_chol = validate_mass(&model)?;
    validate_stiffness_box(&model)?;
    let survey = load_survey(survey_path, &model.dofs)?;
    let plan = load_plan(plan_path, survey.modes.len(), model.dofs.len())?;
    // Enter explicit unavailable optimization state without touching reports.
    let _ = (&m_chol, &plan);
    calibrate_parameters(&model, &survey, &plan, &m_chol)?;
    fail(
        FailureCode::EOptimization,
        "calibration did not produce a durable record",
    )
}

pub fn run_or_exit(cmd: Command) {
    if let Err((code, msg)) = dispatch(cmd) {
        emit_and_exit(code, &msg);
    }
}

pub fn map_path_errors(err: std::io::Error) -> (FailureCode, String) {
    (FailureCode::EPath, err.to_string())
}
