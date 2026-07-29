use serde::Serialize;

pub fn print_json<T: Serialize>(value: &T) {
    println!("{}", serde_json::to_string(value).unwrap_or_else(|_| "{}".into()));
}

pub fn print_ok(msg: &str) {
    println!("ok: {msg}");
}
