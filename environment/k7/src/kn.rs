use std::collections::BTreeMap;

pub type Pair = (String, String);

fn fnv1a32(s: &str) -> u32 {
    let mut h: u32 = 2166136261;
    for b in s.as_bytes() {
        h ^= *b as u32;
        h = h.wrapping_mul(16777619);
    }
    h
}

fn l2_normalize(v: &mut [f64]) {
    let n = v.iter().map(|x| x * x).sum::<f64>().sqrt();
    if n > 0.0 {
        for x in v.iter_mut() {
            *x /= n;
        }
    }
}

pub fn step_x(
    tokens: &[String],
    pairs: &[Pair],
    dim: usize,
    _tau: f64,
    lr: f64,
    steps: usize,
) -> BTreeMap<String, Vec<f64>> {
    let mut emb: BTreeMap<String, Vec<f64>> = BTreeMap::new();
    for t in tokens {
        let mut v = vec![0.0; dim];
        let h = (fnv1a32(t) % 10007) + 1;
        for k in 0..dim {
            v[k] = ((h as f64) * ((k + 1) as f64) * 1e-3).sin();
        }
        l2_normalize(&mut v);
        emb.insert(t.clone(), v);
    }

    for _ in 0..steps {
        for (pa, pp) in pairs {
            let a = emb.get(pa).unwrap().clone();
            let p = emb.get(pp).unwrap().clone();
            let mut mid = vec![0.0; dim];
            for k in 0..dim {
                mid[k] = a[k] - p[k];
            }
            l2_normalize(&mut mid);
            {
                let cur = emb.get_mut(pa).unwrap();
                for k in 0..dim {
                    cur[k] = (1.0 - lr) * cur[k] + lr * mid[k];
                }
                l2_normalize(cur);
            }
            {
                let cur = emb.get_mut(pp).unwrap();
                for k in 0..dim {
                    cur[k] = (1.0 - lr) * cur[k] + lr * mid[k];
                }
            }
        }
    }
    emb
}
