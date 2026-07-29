pub fn utility() -> String { format!("{}+{}", audit_metrics::metrics_id(), audit_trace::trace_id()) }
