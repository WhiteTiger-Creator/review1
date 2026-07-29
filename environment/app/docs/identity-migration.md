# Identity migration

Migrations are signed scoped edges with tenant, namespace pattern, predicate list, and epoch
window. Record fields include `from_principal`, `to_principal`, `subject_principal`,
`namespace_pattern`, `predicates`, and `valid_from_epoch`. Global alias tables are
forbidden; only in-scope migrations rewrite principal identity.
