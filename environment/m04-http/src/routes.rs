use std::sync::Arc;

use axum::extract::{Path, State};
use axum::http::StatusCode;
use axum::routing::{delete, get, post};
use axum::{Json, Router};
use serde::{Deserialize, Serialize};
use serde_json::{json, Value};

use crate::server::AppState;

pub fn build_router(state: Arc<AppState>) -> Router {
    Router::new()
        .route("/v1/records", post(put_record))
        .route("/v1/records/:id", get(get_record))
        .route("/v1/readers", post(open_reader))
        .route("/v1/readers/:token/records/:id", get(reader_get))
        .route("/v1/readers/:token", delete(close_reader))
        .route("/v1/upgrade/start", post(upgrade_start))
        .route("/v1/upgrade/recover", post(upgrade_recover))
        .route("/v1/upgrade/cleanup", post(upgrade_cleanup))
        .route("/v1/status", get(status))
        .with_state(state)
}

#[derive(Deserialize)]
struct PutBody {
    payload: String,
}

#[derive(Serialize)]
struct ErrorBody {
    error: String,
    code: String,
}

async fn put_record(
    State(state): State<Arc<AppState>>,
    Json(body): Json<PutBody>,
) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let record_id = "api-record".to_string();
    let mut store = state.store.lock().unwrap();
    store
        .put_record(&record_id, &body.payload)
        .map_err(api_err)?;
    Ok(Json(json!({"record_id": record_id, "status": "stored"})))
}

async fn get_record(
    State(state): State<Arc<AppState>>,
    Path(id): Path<String>,
) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let store = state.store.lock().unwrap();
    let payload = store.get_record(&id).map_err(api_err)?;
    Ok(Json(json!({"record_id": id, "payload": payload})))
}

async fn open_reader(State(state): State<Arc<AppState>>) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let mut store = state.store.lock().unwrap();
    let snap = store.reader_open().map_err(api_err)?;
    Ok(Json(json!({
        "token": snap.token,
        "reader_id": snap.reader_id,
        "generation_id": snap.generation_id.0,
    })))
}

async fn reader_get(
    State(state): State<Arc<AppState>>,
    Path((token, id)): Path<(String, String)>,
) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let store = state.store.lock().unwrap();
    let payload = store.reader_get(&token, &id).map_err(api_err)?;
    Ok(Json(json!({"token": token, "record_id": id, "payload": payload})))
}

async fn close_reader(
    State(state): State<Arc<AppState>>,
    Path(token): Path<String>,
) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let mut store = state.store.lock().unwrap();
    store.reader_close(&token).map_err(api_err)?;
    Ok(Json(json!({"token": token, "status": "closed"})))
}

async fn upgrade_start(State(state): State<Arc<AppState>>) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let mut store = state.store.lock().unwrap();
    store.upgrade().map_err(api_err)?;
    Ok(Json(json!({"status": "upgraded"})))
}

async fn upgrade_recover(State(state): State<Arc<AppState>>) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let mut store = state.store.lock().unwrap();
    store.recover().map_err(api_err)?;
    Ok(Json(json!({"status": "recovered"})))
}

async fn upgrade_cleanup(State(state): State<Arc<AppState>>) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let mut store = state.store.lock().unwrap();
    store.cleanup().map_err(api_err)?;
    Ok(Json(json!({"status": "cleaned"})))
}

async fn status(State(state): State<Arc<AppState>>) -> Result<Json<Value>, (StatusCode, Json<ErrorBody>)> {
    let store = state.store.lock().unwrap();
    let report = store.status().map_err(api_err)?;
    Ok(Json(serde_json::to_value(report).unwrap_or(json!({}))))
}

fn api_err(err: m01_seal::VaultError) -> (StatusCode, Json<ErrorBody>) {
    let code = match &err {
        m01_seal::VaultError::NotFound(_) => "not_found",
        m01_seal::VaultError::InvalidState(_) => "invalid_state",
        m01_seal::VaultError::Incompatible(_) => "incompatible",
        _ => "error",
    };
    (
        StatusCode::BAD_REQUEST,
        Json(ErrorBody {
            error: err.to_string(),
            code: code.into(),
        }),
    )
}
