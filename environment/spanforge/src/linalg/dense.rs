//! Dense row-major f64 matrices used throughout modal assembly.

#[derive(Clone, Debug)]
pub struct Matrix {
    pub n: usize,
    pub data: Vec<f64>,
}

impl Matrix {
    pub fn zeros(n: usize) -> Self {
        Self {
            n,
            data: vec![0.0; n * n],
        }
    }

    pub fn from_rows(rows: &[Vec<f64>]) -> Result<Self, String> {
        let n = rows.len();
        if n == 0 {
            return Err("empty matrix".into());
        }
        let mut data = Vec::with_capacity(n * n);
        for row in rows {
            if row.len() != n {
                return Err("non-square matrix".into());
            }
            for &v in row {
                if !v.is_finite() {
                    return Err("non-finite matrix entry".into());
                }
                data.push(v);
            }
        }
        Ok(Self { n, data })
    }

    pub fn get(&self, i: usize, j: usize) -> f64 {
        self.data[i * self.n + j]
    }

    pub fn set(&mut self, i: usize, j: usize, v: f64) {
        self.data[i * self.n + j] = v;
    }

    pub fn add_scaled(&mut self, other: &Matrix, scale: f64) {
        debug_assert_eq!(self.n, other.n);
        for k in 0..self.data.len() {
            self.data[k] += scale * other.data[k];
        }
    }

    pub fn clone_scaled(&self, scale: f64) -> Matrix {
        Matrix {
            n: self.n,
            data: self.data.iter().map(|v| v * scale).collect(),
        }
    }

    pub fn symmetrize_checked(&mut self) -> Result<(), String> {
        let n = self.n;
        for i in 0..n {
            for j in (i + 1)..n {
                let a = self.get(i, j);
                let b = self.get(j, i);
                let tol = 1e-12 * a.abs().max(b.abs()).max(1.0);
                if (a - b).abs() > tol {
                    return Err(format!("asymmetric entries at ({i},{j})"));
                }
                let mean = 0.5 * (a + b);
                self.set(i, j, mean);
                self.set(j, i, mean);
            }
        }
        Ok(())
    }

    pub fn permute(&self, order: &[usize]) -> Matrix {
        let n = self.n;
        let mut out = Matrix::zeros(n);
        for (ni, &oi) in order.iter().enumerate() {
            for (nj, &oj) in order.iter().enumerate() {
                out.set(ni, nj, self.get(oi, oj));
            }
        }
        out
    }

    pub fn mul_vec(&self, x: &[f64]) -> Vec<f64> {
        let mut y = vec![0.0; self.n];
        for i in 0..self.n {
            let mut s = 0.0;
            for j in 0..self.n {
                s += self.get(i, j) * x[j];
            }
            y[i] = s;
        }
        y
    }

    pub fn quadratic(&self, x: &[f64]) -> f64 {
        let y = self.mul_vec(x);
        x.iter().zip(y.iter()).map(|(a, b)| a * b).sum()
    }
}

pub fn dot(a: &[f64], b: &[f64]) -> f64 {
    a.iter().zip(b.iter()).map(|(x, y)| x * y).sum()
}

pub fn axpy(a: f64, x: &[f64], y: &mut [f64]) {
    for i in 0..y.len() {
        y[i] += a * x[i];
    }
}

pub fn scale_inplace(x: &mut [f64], s: f64) {
    for v in x.iter_mut() {
        *v *= s;
    }
}

pub fn norm2(x: &[f64]) -> f64 {
    dot(x, x).sqrt()
}

pub fn format_f64(v: f64) -> String {
    let mut x = v;
    if x == 0.0 {
        x = 0.0;
    }
    let s = format!("{}", x);
    if s == "-0" {
        "0".into()
    } else {
        s
    }
}
