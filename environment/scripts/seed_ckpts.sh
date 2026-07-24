#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BIN="${ROOT}/bin/x7_orch"
OUT="${ROOT}/fixtures/ckpts"
mkdir -p "${OUT}"

seed_one() {
  local tag="$1"
  local np="$2"
  local cfg="${ROOT}/cfg_store/cfg_${tag}.json"
  local prof="${ROOT}/profiles/px.prof"
  local dst="${OUT}/${tag}_ckpt_n${np}.h5"
  rm -f "${dst}"
  mpirun --allow-run-as-root --oversubscribe -np "${np}" "${BIN}" \
    --mode continuous \
    --cfg "${cfg}" \
    --profile "${prof}" \
    --write-ckpt "${dst}" \
    --final /tmp/x7_seed_final.h5 \
    --stage /tmp/x7_seed_stage
  if [[ "${np}" == "2" ]]; then
    cp -f "${dst}" "${OUT}/${tag}_ckpt.h5"
  fi
}

for tag in sa sb sc; do
  seed_one "${tag}" 2
  seed_one "${tag}" 3
done

export X7_FIXTURE_ROOT="${OUT}"
python3 - <<'PY'
import h5py
import os
import shutil
import numpy as np

root = os.environ["X7_FIXTURE_ROOT"]

def poison(path: str) -> None:
    with h5py.File(path, "a") as f:
        keys = [k for k in f.keys() if k.startswith("gen_")]
        if not keys:
            raise SystemExit(f"missing gen in {path}")
        g1 = f[sorted(keys)[0]]
        if "gen_0002" in f:
            del f["gen_0002"]
        g2 = f.create_group("gen_0002")
        for k, v in g1.attrs.items():
            g2.attrs[k] = v
        g2.attrs["gen_id"] = 2
        g2.attrs["committed"] = 0
        for name in g1:
            if name.startswith("r0_"):
                g2.create_dataset(name, data=g1[name][...])

def shuffle_gids(path: str, out: str) -> None:
    if os.path.exists(out):
        os.remove(out)
    shutil.copyfile(path, out)
    with h5py.File(out, "a") as f:
        g = f[sorted(k for k in f.keys() if k.startswith("gen_"))[0]]
        nproc = int(g.attrs.get("nproc_write", 1))
        for r in range(nproc):
            owned = g[f"r{r}_owned"][...]
            gids = g[f"r{r}_gids"][...]
            order = np.array(range(len(gids)))
            if len(order) > 1:
                order = order[::-1]
            g[f"r{r}_owned"][...] = owned[order]
            g[f"r{r}_gids"][...] = gids[order]
            hi = g[f"r{r}_ghost_hi"][...]
            hi[:] = 1.0e6
            g[f"r{r}_ghost_hi"][...] = hi

for tag in ("sa", "sb", "sc"):
    for np_ in (2, 3):
        path = os.path.join(root, f"{tag}_ckpt_n{np_}.h5")
        poison(path)
    alias = os.path.join(root, f"{tag}_ckpt.h5")
    shutil.copyfile(os.path.join(root, f"{tag}_ckpt_n2.h5"), alias)
    shuffle_gids(alias, os.path.join(root, f"{tag}_shuffled.h5"))

legacy_src = os.path.join(root, "sa_ckpt_n2.h5")
legacy_dst = os.path.join(root, "legacy_sa.h5")
if os.path.exists(legacy_dst):
    os.remove(legacy_dst)
with h5py.File(legacy_src, "r") as src, h5py.File(legacy_dst, "w") as dst:
    g = src[sorted(k for k in src.keys() if k.startswith("gen_"))[0]]
    dst.attrs["layout"] = 1
    for k in ("gen_id", "step", "nproc_write", "committed"):
        dst.attrs[k] = g.attrs[k]
    if "fingerprint" in g.attrs:
        dst.attrs["fingerprint"] = g.attrs["fingerprint"]
    if "field_cksum" in g.attrs:
        dst.attrs["field_cksum"] = g.attrs["field_cksum"]
    nproc = int(g.attrs.get("nproc_write", 2))
    for r in range(nproc):
        for suffix in ("owned", "ghost_lo", "ghost_hi", "gids"):
            sname = f"r{r}_{suffix}"
            dname = f"{suffix}_r{r}"
            if sname in g:
                dst.create_dataset(dname, data=g[sname][...])
    hist = g["hist"] if "hist" in g else src.get("hist")
    if hist is not None:
        hg = dst.create_group("hist")
        for name in ("dt_seq", "mass_seq"):
            if name in hist:
                hg.create_dataset(name, data=hist[name][...])
        if "step" in hist.attrs:
            hg.attrs["step"] = hist.attrs["step"]
    ctrl = g["ctrl"] if "ctrl" in g else src.get("ctrl")
    if ctrl is not None:
        for k in ("last_dt", "n_reject", "n_accept", "accum"):
            if k in ctrl.attrs:
                dst.attrs[f"ctrl_{k}"] = ctrl.attrs[k]
print("seeded", root)
PY
