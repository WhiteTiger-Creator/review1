#!/usr/bin/env bash
set -euo pipefail

ROOT="/app/environment"
BIN="${ROOT}/bin/x7_orch"
STAGE="/app/output/stage"
FINAL="/app/output/final.h5"
RECORD="/app/output/run-record.json"
mkdir -p "${STAGE}" "$(dirname "${FINAL}")"

if [[ "${X7_PURGE:-1}" == "1" ]]; then
  bash "${ROOT}/migrations/purge_x7.sh"
fi

declare -a SCENARIOS=(sa sb sc)
declare -a PROFILES=(px qy)
declare -a TRANS=(n2_to_n5 n5_to_n3 n3_to_n4 n4_same)

np_write() {
  case "$1" in
    n2_to_n5) echo 2 ;;
    n5_to_n3) echo 5 ;;
    n3_to_n4) echo 3 ;;
    n4_same) echo 4 ;;
    *) echo 2 ;;
  esac
}

np_read() {
  case "$1" in
    n2_to_n5) echo 5 ;;
    n5_to_n3) echo 3 ;;
    n3_to_n4) echo 4 ;;
    n4_same) echo 4 ;;
    *) echo 2 ;;
  esac
}

poison_incomplete() {
  local src="$1"
  if [[ ! -f "${src}" ]]; then
    echo "poison_incomplete: missing ${src}" >&2
    return 1
  fi
  python3 - "$src" <<'PY'
import h5py, sys
path = sys.argv[1]
with h5py.File(path, "r+") as f:
    keys = [k for k in f.keys() if k.startswith("gen_")]
    if not keys:
        raise SystemExit("missing gen group")
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
PY
}

to_legacy() {
  local src="$1"
  local dst="$2"
  python3 - "$src" "$dst" <<'PY'
import h5py, os, sys
src, dst = sys.argv[1], sys.argv[2]
if os.path.exists(dst):
    os.remove(dst)
with h5py.File(src, "r") as s, h5py.File(dst, "w") as d:
    keys = [k for k in s.keys() if k.startswith("gen_")]
    g = s[sorted(keys)[0]]
    d.attrs["layout"] = 1
    for k in ("gen_id", "step", "nproc_write", "committed"):
        if k in g.attrs:
            d.attrs[k] = g.attrs[k]
    if "fingerprint" in g.attrs:
        d.attrs["fingerprint"] = g.attrs["fingerprint"]
    if "field_cksum" in g.attrs:
        d.attrs["field_cksum"] = g.attrs["field_cksum"]
    nproc = int(g.attrs.get("nproc_write", 2))
    for r in range(nproc):
        for suffix in ("owned", "ghost_lo", "ghost_hi", "gids"):
            sname = f"r{r}_{suffix}"
            dname = f"{suffix}_r{r}"
            if sname in g:
                d.create_dataset(dname, data=g[sname][...])
    hist_src = None
    if "hist" in g:
        hist_src = g["hist"]
    elif "hist" in s:
        hist_src = s["hist"]
    if hist_src is not None:
        hg = d.create_group("hist")
        for name in ("dt_seq", "mass_seq"):
            if name in hist_src:
                hg.create_dataset(name, data=hist_src[name][...])
        if "step" in hist_src.attrs:
            hg.attrs["step"] = hist_src.attrs["step"]
    ctrl_src = None
    if "ctrl" in g:
        ctrl_src = g["ctrl"]
    elif "ctrl" in s:
        ctrl_src = s["ctrl"]
    if ctrl_src is not None:
        for k in ("last_dt", "n_reject", "n_accept", "accum"):
            if k in ctrl_src.attrs:
                d.attrs[f"ctrl_{k}"] = ctrl_src.attrs[k]
PY
}

for scen in "${SCENARIOS[@]}"; do
  for prof in "${PROFILES[@]}"; do
    for tr in "${TRANS[@]}"; do
      cell="${scen}_${prof}_${tr}"
      cfg="${ROOT}/cfg_store/cfg_${scen}.json"
      penv="${ROOT}/profiles/${prof}.prof"
      nwrite="$(np_write "${tr}")"
      ncont="$(np_read "${tr}")"
      cell_stage="${STAGE}/${cell}"
      mkdir -p "${cell_stage}"
      ckpt="${cell_stage}/ckpt.h5"
      rm -f "${ckpt}"

      mpirun --allow-run-as-root --oversubscribe -np "${ncont}" "${BIN}" \
        --mode continuous \
        --cfg "${cfg}" \
        --profile "${penv}" \
        --stage "${cell_stage}/uninterrupted" \
        --final "${cell_stage}/uninterrupted/final.h5"

      mpirun --allow-run-as-root --oversubscribe -np "${nwrite}" "${BIN}" \
        --mode continuous \
        --cfg "${cfg}" \
        --profile "${penv}" \
        --write-ckpt "${ckpt}" \
        --stage "${cell_stage}/writer" \
        --final "${cell_stage}/writer/final.h5"
      test -f "${ckpt}"

      poison_incomplete "${ckpt}"
      if [[ "${scen}" == "sa" && "${prof}" == "qy" ]]; then
        leg="${cell_stage}/legacy.h5"
        to_legacy "${ckpt}" "${leg}"
        ckpt="${leg}"
        test -f "${ckpt}"
      fi

      bash "${ROOT}/migrations/purge_x7.sh" "${cell_stage}/continue"

      mpirun --allow-run-as-root --oversubscribe -np "${ncont}" "${BIN}" \
        --mode continue \
        --cfg "${cfg}" \
        --profile "${penv}" \
        --ckpt "${ckpt}" \
        --stage "${cell_stage}/continue" \
        --final "${cell_stage}/continue/final.h5"
      test -f "${cell_stage}/continue/final.h5"
    done
  done
done

cp "${STAGE}/sc_qy_n4_same/continue/final.h5" "${FINAL}" 2>/dev/null || \
  cp "${STAGE}/sa_px_n4_same/continue/final.h5" "${FINAL}" 2>/dev/null || true

"${ROOT}/tools/x7_gate" --matrix-full --out "${RECORD}" --final "${FINAL}" --stage "${STAGE}"
