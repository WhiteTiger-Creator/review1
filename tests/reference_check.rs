//! Standalone ground-truth checker for the fleet-rotation-log-repair task.
//!
//! Independently re-implements the same "minimum tag corrections" and
//! "is this array producible" computation the task's solution/solve.sh
//! implements, so test_outputs.py can cross-check an agent's submission
//! without trusting its own arithmetic. Compiled at test time by
//! tests/test.sh (rustc is already baked into the image) — never shipped
//! to the agent.
//!
//! Reads the same batch format as `rotctl repair` (see
//! environment/app/docs/rotation-contract.md) from stdin, and for each
//! window prints a single line: the minimum number of tag corrections
//! needed to make that window producible. Feeding a candidate corrected
//! array back through this checker and confirming it prints 0 is how
//! test_outputs.py verifies a submitted array is actually producible, not
//! just "close" to the original.
//!
//! Single-file, std-only, no external crates — compiled directly with
//! `rustc`, no Cargo project needed.

use std::io::{self, Read, Write};

const NEG_INF: i64 = -1_000_000_000;

#[derive(Clone, Copy, PartialEq, Eq)]
enum Link {
    Start,
    SameAnchor,
    Reset,
    Weak,
}

struct FreeSlots {
    parent: Vec<usize>,
}

impl FreeSlots {
    fn new(n: usize) -> Self {
        FreeSlots {
            parent: (0..=n).collect(),
        }
    }

    fn find(&mut self, x: usize) -> usize {
        let mut root = x;
        while self.parent[root] != root {
            root = self.parent[root];
        }
        let mut cur = x;
        while self.parent[cur] != root {
            let next = self.parent[cur];
            self.parent[cur] = root;
            cur = next;
        }
        root
    }

    fn fill(&mut self, x: usize) {
        self.parent[x] = x + 1;
    }
}

fn longest_kept_chain(n: usize, m: usize, a: &[i64]) -> (i64, Vec<(usize, usize, Link)>) {
    let mut pref = vec![NEG_INF; n + 1];
    let mut suf = vec![NEG_INF; n + 1];
    let mut dpvl = vec![NEG_INF; n + 1];
    pref[0] = 0;

    let mut pref_bp: Vec<i64> = vec![-1; n + 1];
    let mut suf_bp: Vec<i64> = vec![-1; n + 1];
    let mut dpvl_bp: Vec<i64> = vec![-1; n + 1];

    let mut parent: Vec<i64> = vec![-1; n];
    let mut link: Vec<Link> = vec![Link::Start; n];

    for i in 0..n {
        let anchor: i64 = i as i64 - a[i];

        let mut best_val = suf[i];
        let mut best_bp = suf_bp[i];
        let mut best_link = Link::Weak;

        if anchor >= 0 {
            let l = anchor as usize;
            if dpvl[l] > best_val {
                best_val = dpvl[l];
                best_bp = dpvl_bp[l];
                best_link = Link::SameAnchor;
            }
            if pref[l] > best_val {
                best_val = pref[l];
                best_bp = pref_bp[l];
                best_link = Link::Reset;
            }
        }

        let c = best_val + 1;
        parent[i] = best_bp;
        link[i] = best_link;

        if c > pref[i] {
            pref[i + 1] = c;
            pref_bp[i + 1] = i as i64;
        } else {
            pref[i + 1] = pref[i];
            pref_bp[i + 1] = pref_bp[i];
        }

        if suf[i] > suf[i + 1] {
            suf[i + 1] = suf[i];
            suf_bp[i + 1] = suf_bp[i];
        }

        if anchor >= 0 {
            let l = anchor as usize;
            if c > dpvl[l] {
                dpvl[l] = c;
                dpvl_bp[l] = i as i64;
            }
            if l + m <= n && c > suf[l + m] {
                suf[l + m] = c;
                suf_bp[l + m] = i as i64;
            }
        }
    }

    let kept = std::cmp::max(suf[n], 0);
    if kept <= 0 {
        return (kept, Vec::new());
    }

    let mut slots: Vec<usize> = Vec::with_capacity(kept as usize);
    let mut cur = suf_bp[n];
    while cur != -1 {
        slots.push(cur as usize);
        cur = parent[cur as usize];
    }
    slots.reverse();

    let mut chain = Vec::with_capacity(slots.len());
    for (idx, &slot) in slots.iter().enumerate() {
        let anchor = slot - a[slot] as usize;
        let this_link = if idx == 0 { Link::Start } else { link[slot] };
        chain.push((slot, anchor, this_link));
    }
    (kept, chain)
}

struct Segment {
    anchor: usize,
    block: usize,
}

fn group_into_blocks(chain: &[(usize, usize, Link)]) -> Vec<Segment> {
    let mut segments: Vec<Segment> = Vec::new();
    let mut block: i64 = -1;
    let mut anchor = 0usize;

    for &(_slot, a, l) in chain {
        match l {
            Link::Start | Link::Reset => {
                block += 1;
                anchor = a;
                segments.push(Segment {
                    anchor,
                    block: block as usize,
                });
            }
            Link::SameAnchor => debug_assert_eq!(a, anchor),
            Link::Weak => {
                anchor = a;
                segments.push(Segment {
                    anchor,
                    block: block as usize,
                });
            }
        }
    }
    segments
}

fn repair(n: usize, m: usize, a: &[u32]) -> (usize, Vec<u32>) {
    let zeroed: Vec<i64> = a.iter().map(|&x| x as i64 - 1).collect();
    let (kept, chain) = longest_kept_chain(n, m, &zeroed);
    let corrections = n - kept as usize;

    let mut result: Vec<i64> = vec![-1; n];
    let mut free = FreeSlots::new(n);

    if !chain.is_empty() {
        let mut segments = group_into_blocks(&chain);
        segments.sort_by(|x, y| y.block.cmp(&x.block).then(x.anchor.cmp(&y.anchor)));

        for seg in &segments {
            let l = seg.anchor;
            let hi = std::cmp::min(l + m - 1, n - 1);
            let mut pos = free.find(l);
            while pos <= hi {
                result[pos] = (pos - l) as i64;
                free.fill(pos);
                pos = free.find(pos);
            }
        }
    }

    loop {
        let pos = free.find(0);
        if pos >= n {
            break;
        }
        let l = std::cmp::min(pos, n - m);
        let hi = std::cmp::min(l + m - 1, n - 1);
        let mut p = free.find(l);
        while p <= hi {
            result[p] = (p - l) as i64;
            free.fill(p);
            p = free.find(p);
        }
    }

    let corrected: Vec<u32> = result.iter().map(|&v| (v + 1) as u32).collect();
    (corrections, corrected)
}

fn main() {
    let mut input = String::new();
    io::stdin()
        .read_to_string(&mut input)
        .expect("failed to read stdin");

    let mut tokens = input
        .split_ascii_whitespace()
        .map(|tok| tok.parse::<i64>().expect("malformed integer in input"));

    let window_count = tokens.next().expect("missing window count") as usize;

    let mut out = String::new();
    for _ in 0..window_count {
        let n = tokens.next().expect("missing slot count") as usize;
        let m = tokens.next().expect("missing batch size") as usize;
        let tags: Vec<u32> = (0..n)
            .map(|_| tokens.next().expect("missing slot tag") as u32)
            .collect();

        let (corrections, _fixed) = repair(n, m, &tags);
        out.push_str(&corrections.to_string());
        out.push('\n');
    }

    io::stdout()
        .write_all(out.as_bytes())
        .expect("failed to write stdout");
}
