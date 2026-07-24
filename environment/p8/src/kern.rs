use crate::rowv::LoadSpec;

pub fn idx_v(node: usize) -> usize {
    2 * node
}

pub fn idx_th(node: usize) -> usize {
    2 * node + 1
}

/// Build local flexure contribution from span length and flexural rigidity.
/// Laid out as separate transverse / rotation blocks (not a flat textbook dump).
fn flex_pack(ei: f64, h: f64, out: &mut [f64; 16]) {
    let a = 12.0 * ei / (h * h * h);
    let b = 6.0 * ei / (h * h);
    let c = 4.0 * ei / h;
    let d = 2.0 * ei / h;
    // Row-major [v1, th1, v2, th2]
    out[0] = a;
    out[1] = b;
    out[2] = -a;
    out[3] = b;
    out[4] = b;
    out[5] = c;
    out[6] = -b;
    out[7] = d;
    out[8] = -a;
    out[9] = -b;
    out[10] = a;
    out[11] = -b;
    out[12] = b;
    out[13] = d;
    out[14] = -b;
    out[15] = c;
}

/// Consistent nodal forces for a point action at global x.
pub fn apply_point(f: &mut [f64], len: f64, n_elem: usize, x: f64, p: f64) {
    let h = len / n_elem as f64;
    let mut xx = x.clamp(0.0, len);
    let mut e = ((xx / h).floor() as usize).min(n_elem - 1);
    let mut xi = xx - e as f64 * h;
    if (xi - h).abs() < 1e-12 && e + 1 < n_elem {
        e += 1;
        xi = 0.0;
        xx = e as f64 * h;
    }
    let n1 = 1.0 - 3.0 * (xi * xi) / (h * h) + 2.0 * (xi * xi * xi) / (h * h * h);
    let n2 = xi - 2.0 * (xi * xi) / h + (xi * xi * xi) / (h * h);
    let n3 = 3.0 * (xi * xi) / (h * h) - 2.0 * (xi * xi * xi) / (h * h * h);
    let n4 = -(xi * xi) / h + (xi * xi * xi) / (h * h);
    let i0 = idx_v(e);
    let i1 = idx_th(e);
    let i2 = idx_v(e + 1);
    let i3 = idx_th(e + 1);
    f[i0] += p * n1;
    f[i1] += p * n2;
    f[i2] += p * n3;
    f[i3] += p * n4;
    let _ = xx;
}

pub fn fill_system_ref(len: f64, ei: f64, n_elem: usize, loads: &[LoadSpec]) -> (Vec<Vec<f64>>, Vec<f64>) {
    let n_node = n_elem + 1;
    let ndof = 2 * n_node;
    let mut k = vec![vec![0.0; ndof]; ndof];
    let mut f = vec![0.0; ndof];
    let h = len / n_elem as f64;
    let mut buf = [0.0_f64; 16];
    for e in 0..n_elem {
        flex_pack(ei, h, &mut buf);
        let map = [idx_v(e), idx_th(e), idx_v(e + 1), idx_th(e + 1)];
        for r in 0..4 {
            for c in 0..4 {
                k[map[r]][map[c]] += buf[r * 4 + c];
            }
        }
    }
    for load in loads {
        apply_point(&mut f, len, n_elem, load.x_m, load.force_n);
    }
    (k, f)
}

pub fn mid_v(u: &[f64], len: f64, n_elem: usize) -> f64 {
    let h = len / n_elem as f64;
    let mid = 0.5 * len;
    let mut e = ((mid / h).floor() as usize).min(n_elem - 1);
    let mut xi = mid - e as f64 * h;
    if (xi - h).abs() < 1e-12 && e + 1 < n_elem {
        e += 1;
        xi = 0.0;
    }
    let v1 = u[idx_v(e)];
    let t1 = u[idx_th(e)];
    let v2 = u[idx_v(e + 1)];
    let t2 = u[idx_th(e + 1)];
    let n1 = 1.0 - 3.0 * (xi * xi) / (h * h) + 2.0 * (xi * xi * xi) / (h * h * h);
    let n2 = xi - 2.0 * (xi * xi) / h + (xi * xi * xi) / (h * h);
    let n3 = 3.0 * (xi * xi) / (h * h) - 2.0 * (xi * xi * xi) / (h * h * h);
    let n4 = -(xi * xi) / h + (xi * xi * xi) / (h * h);
    n1 * v1 + n2 * t1 + n3 * v2 + n4 * t2
}

/// Dense reduced solve with pinned transverse DOFs.
pub fn solve_reduced(k: &[Vec<f64>], f: &[f64], pinned: &[usize]) -> Vec<f64> {
    let n = f.len();
    let mut free: Vec<usize> = (0..n).filter(|i| !pinned.contains(i)).collect();
    free.sort_unstable();
    let m = free.len();
    let mut a = vec![vec![0.0; m]; m];
    let mut b = vec![0.0; m];
    for (ri, &gi) in free.iter().enumerate() {
        b[ri] = f[gi];
        for (ci, &gj) in free.iter().enumerate() {
            a[ri][ci] = k[gi][gj];
        }
    }
    for col in 0..m {
        let mut piv = col;
        for r in (col + 1)..m {
            if a[r][col].abs() > a[piv][col].abs() {
                piv = r;
            }
        }
        if piv != col {
            a.swap(piv, col);
            b.swap(piv, col);
        }
        let diag = a[col][col];
        if diag.abs() < 1e-18 {
            continue;
        }
        for r in (col + 1)..m {
            let factor = a[r][col] / diag;
            for c in col..m {
                a[r][c] -= factor * a[col][c];
            }
            b[r] -= factor * b[col];
        }
    }
    let mut y = vec![0.0; m];
    for i in (0..m).rev() {
        let mut s = b[i];
        for j in (i + 1)..m {
            s -= a[i][j] * y[j];
        }
        y[i] = if a[i][i].abs() < 1e-18 {
            0.0
        } else {
            s / a[i][i]
        };
    }
    let mut u = vec![0.0; n];
    for (i, &gi) in free.iter().enumerate() {
        u[gi] = y[i];
    }
    u
}
