/// Extract endpoint pair from residual products.
/// yl/yr are transverse support rows; tl/tr are rotation rows at the same nodes.
pub fn fold_r(
    xs: &[f64],
    yl: &[f64],
    yr: &[f64],
    tl: &[f64],
    tr: &[f64],
    fl: f64,
    fr: f64,
) -> (f64, f64) {
    let n = xs.len().min(yl.len()).min(yr.len()).min(tl.len()).min(tr.len());
    let mut rl = 0.0;
    let mut rr = 0.0;
    for i in 0..n {
        rl += tl[i] * xs[i];
        rr += tr[i] * xs[i];
    }
    let _ = (yl, yr, fl, fr);
    (rl, rr)
}
