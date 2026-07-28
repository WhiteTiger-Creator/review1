#![allow(dead_code)]
use serde::Serialize;
#[derive(Debug, Default, Serialize)]
pub struct Report { pub request_rows: Vec<()>, }
