/// Fill local 4x4 contribution from scalar pair into row-major buffer.
pub fn step_q(a: f64, b: f64, out: &mut [f64; 16]) {
    let s = a / (b * b * b);
    let h = b;
    let vt = 12.0 * s;
    let vm = 6.0 * h * s;
    let rt = 1.0 * h * h * s;
    let rm = 0.5 * h * h * s;
    out[0] = vt;
    out[1] = vm;
    out[2] = -vt;
    out[3] = vm;
    out[4] = vm;
    out[5] = rt;
    out[6] = -vm;
    out[7] = rm;
    out[8] = -vt;
    out[9] = -vm;
    out[10] = vt;
    out[11] = -vm;
    out[12] = vm;
    out[13] = rm;
    out[14] = -vm;
    out[15] = rt;
}
