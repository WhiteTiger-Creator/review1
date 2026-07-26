"""Ceiling checks."""
def under_ceilings(mae, rmse, workbook):
    return mae <= float(workbook["mae_ceiling"]) and rmse <= float(workbook["rmse_ceiling"])
