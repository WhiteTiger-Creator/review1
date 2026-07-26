# OLS beta

Solve w = (XᵀX)⁻¹ Xᵀy on learning rows only. No ridge λ, even when the workbook carries a ridge_lambda field.

Load design rows from the on-disk design vault. Learning row order for the design matrix X follows ascending specimen id.

Store hwml.beta/v1 with names and trunc_decimals-rounded values.
---

Scheme id: hwml.beta/v1

Learning rows use ascending id sequence before the Gram solve. Digests are SHA-256 hex of on-disk vault/beta bytes.
