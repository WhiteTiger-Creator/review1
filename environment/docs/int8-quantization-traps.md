# INT8 quantization traps for certifiers

Common pitfalls when walking INT8 variants:

- Using full scale as half-width instead of scale divided by two per coefficient
- Forgetting bias uncertainty when summing affine error budgets
- Sorting layers alphabetically instead of dependency order
- Treating epoch-two ceilings as inclusive rather than strict
- Comparing raw pre-persistence floats instead of measured_drift from %.6f endpoints
