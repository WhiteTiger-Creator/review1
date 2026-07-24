//! Eigenvalue and measured-frequency clustering.

#[derive(Clone, Debug)]
pub struct Cluster {
    pub start: usize,
    pub end: usize, // exclusive
    pub member_indices: Vec<usize>,
    pub centroid_hz: f64,
}

pub fn relative_close(a: f64, b: f64, tol: f64) -> bool {
    let den = a.abs().max(b.abs()).max(1.0);
    (a - b).abs() / den <= tol
}

pub fn cluster_by_values(values: &[f64], freqs_hz: &[f64], tol: f64) -> Vec<Cluster> {
    let mut clusters = Vec::new();
    if values.is_empty() {
        return clusters;
    }
    let mut start = 0usize;
    for i in 1..values.len() {
        if !relative_close(values[i], values[i - 1], tol) {
            let members: Vec<usize> = (start..i).collect();
            let centroid = members.iter().map(|&j| freqs_hz[j]).sum::<f64>() / members.len() as f64;
            clusters.push(Cluster {
                start,
                end: i,
                member_indices: members,
                centroid_hz: centroid,
            });
            start = i;
        }
    }
    let members: Vec<usize> = (start..values.len()).collect();
    let centroid = members.iter().map(|&j| freqs_hz[j]).sum::<f64>() / members.len() as f64;
    clusters.push(Cluster {
        start,
        end: values.len(),
        member_indices: members,
        centroid_hz: centroid,
    });
    clusters
}

pub fn cluster_ranges(clusters: &[Cluster]) -> Vec<(usize, usize)> {
    clusters.iter().map(|c| (c.start, c.end)).collect()
}

/// Measured clustering uses squared angular frequencies.
pub fn measured_cluster_keys(freqs_hz: &[f64]) -> Vec<f64> {
    freqs_hz
        .iter()
        .map(|f| {
            let w = 2.0 * std::f64::consts::PI * f;
            w * w
        })
        .collect()
}
