#!/bin/bash
set -euo pipefail

ENV_ROOT="/app/environment"
cd "${ENV_ROOT}"

python3 - <<'PY'
from pathlib import Path

root = Path("/app/environment")

# --- catalog: newest recoverable via validate ---
(root / "storage/catalog.cpp").write_text(r'''#include "catalog.hpp"

#include "io.hpp"
#include "layout.hpp"
#include "validate.hpp"

#include <algorithm>
#include <stdexcept>
#include <vector>

GenRec stor_catalog_select(const Bag& bag) {
    std::vector<int> ids;
    stor_io::list_gen_ids(bag.store_path, ids);
    if (ids.empty()) {
        throw std::runtime_error("catalog: no generations");
    }
    std::sort(ids.begin(), ids.end(), std::greater<int>());
    for (int id : ids) {
        GenRec gen{};
        stor_layout::load_meta(bag.store_path, id, gen);
        gen.store_path = bag.store_path;
        if (stor_validate_generation(bag, gen)) {
            return gen;
        }
    }
    throw std::runtime_error("catalog: no recoverable generation");
}
''')

# --- validate: full recoverability ---
(root / "storage/validate.cpp").write_text(r'''#include "validate.hpp"

#include "io.hpp"
#include "layout.hpp"

#include "../core/advance.hpp"

#include <cmath>
#include <vector>

bool stor_validate_generation(const Bag& bag, const GenRec& gen) {
    if (gen.marker != 1) {
        return false;
    }
    if (gen.layout_ver < 1 || gen.layout_ver > 3) {
        return false;
    }
    if (!bag.fingerprint_want.empty() && !gen.fingerprint.empty() &&
        gen.fingerprint != bag.fingerprint_want) {
        return false;
    }

    std::vector<int> coverage(static_cast<size_t>(bag.n_global), 0);
    std::vector<double> global(static_cast<size_t>(bag.n_global), 0.0);
    for (int r = 0; r < gen.nproc_write; ++r) {
        std::vector<double> owned, glo, ghi;
        std::vector<int> gids;
        try {
            stor_layout::load_rank(gen.store_path, gen, r, owned, glo, ghi, gids);
        } catch (...) {
            return false;
        }
        if (owned.size() != gids.size()) {
            return false;
        }
        for (size_t i = 0; i < gids.size(); ++i) {
            const int g = gids[i];
            if (g < 0 || g >= bag.n_global) {
                return false;
            }
            if (coverage[static_cast<size_t>(g)] != 0) {
                return false;
            }
            coverage[static_cast<size_t>(g)] = 1;
            if (!std::isfinite(owned[i])) {
                return false;
            }
            global[static_cast<size_t>(g)] = owned[i];
        }
    }
    for (int c : coverage) {
        if (c != 1) {
            return false;
        }
    }

    HistRec hist{};
    CtrlState ctrl{};
    stor_layout::load_hist_ctrl(gen.store_path, gen, hist, ctrl);
    if (static_cast<int>(hist.dt_seq.size()) != gen.step) {
        return false;
    }
    if (ctrl.n_accept != gen.step) {
        return false;
    }
    if (!(ctrl.last_dt > 0.0) || !std::isfinite(ctrl.accum)) {
        return false;
    }

    const double ck = adv_field_cksum(global);
    if (gen.layout_ver >= 3 || gen.field_cksum != 0.0) {
        if (std::fabs(ck - gen.field_cksum) > 1e-9) {
            return false;
        }
    }
    return true;
}
''')

# --- reconstruct: GID placement, ignore halos ---
(root / "restart/reconstruct.cpp").write_text(r'''#include "reconstruct.hpp"

#include "../storage/layout.hpp"

#include <stdexcept>
#include <vector>

GlobRec restart_reconstruct(const GenRec& gen, const Bag& bag) {
    GlobRec out{};
    out.ncell = bag.n_global;
    out.step = gen.step;
    out.vals.assign(static_cast<size_t>(bag.n_global), 0.0);
    out.gids.clear();

    std::vector<int> seen(static_cast<size_t>(bag.n_global), 0);
    for (int r = 0; r < gen.nproc_write; ++r) {
        std::vector<double> owned, glo, ghi;
        std::vector<int> gids;
        stor_layout::load_rank(gen.store_path, gen, r, owned, glo, ghi, gids);
        (void)glo;
        (void)ghi;
        for (size_t i = 0; i < gids.size(); ++i) {
            const int g = gids[i];
            if (g < 0 || g >= bag.n_global) {
                throw std::runtime_error("reconstruct: gid out of range");
            }
            out.vals[static_cast<size_t>(g)] = owned[i];
            seen[static_cast<size_t>(g)] = 1;
        }
    }
    for (int i = 0; i < bag.n_global; ++i) {
        if (!seen[static_cast<size_t>(i)]) {
            throw std::runtime_error("reconstruct: incomplete coverage");
        }
        out.gids.push_back(i);
    }

    HistRec hist{};
    CtrlState ctrl{};
    stor_layout::load_hist_ctrl(gen.store_path, gen, hist, ctrl);
    out.dt_seq = hist.dt_seq;
    out.m_seq = hist.m_seq;
    out.ctrl = ctrl;
    return out;
}
''')

# --- partition: rem-aware decompose ---
(root / "restart/partition.cpp").write_text(r'''#include "partition.hpp"

#include "../core/advance.hpp"

DistRec restart_partition(const GlobRec& glob, int nproc, int rank) {
    DistRec dist{};
    dist.rank = rank;
    dist.nproc = nproc;
    dist.step = glob.step;
    dist.dx = adv_dx(glob.ncell);

    int lo = 0, hi = 0, loc_n = 0;
    adv_decompose(glob.ncell, nproc, rank, lo, hi, loc_n);
    dist.owned.resize(static_cast<size_t>(loc_n));
    dist.gids.resize(static_cast<size_t>(loc_n));
    dist.ghost_lo = {0.0};
    dist.ghost_hi = {0.0};
    for (int i = 0; i < loc_n; ++i) {
        const int g = lo + i;
        dist.owned[static_cast<size_t>(i)] = glob.vals[static_cast<size_t>(g)];
        dist.gids[static_cast<size_t>(i)] = g;
    }
    if (loc_n > 0) {
        dist.ghost_lo[0] = (lo == 0) ? 0.0 : glob.vals[static_cast<size_t>(lo - 1)];
        dist.ghost_hi[0] =
            (hi == glob.ncell - 1) ? 0.0 : glob.vals[static_cast<size_t>(hi + 1)];
    }
    return dist;
}
''')

# --- controller: restore + adaptive accept/reject ---
(root / "numerics/controller.cpp").write_text(r'''#include "controller.hpp"

#include "../core/advance.hpp"

#include <mpi.h>

#include <algorithm>
#include <cmath>
#include <vector>

CtrlState num_ctrl_defaults(const ProfKnobs& prof, double kappa, double dx) {
    CtrlState c{};
    c.last_dt = adv_pick_dt(kappa, dx, prof.dt0, prof.cfl);
    c.n_reject = 0;
    c.n_accept = 0;
    c.accum = 1.0;
    return c;
}

namespace {

void halo_exchange(std::vector<double>& owned, std::vector<double>& glo, std::vector<double>& ghi,
                   int rank, int nproc) {
    MPI_Status st;
    if (rank > 0) {
        MPI_Sendrecv(owned.data(), 1, MPI_DOUBLE, rank - 1, 11, glo.data(), 1, MPI_DOUBLE, rank - 1,
                     12, MPI_COMM_WORLD, &st);
    } else {
        glo[0] = 0.0;
    }
    if (rank < nproc - 1) {
        MPI_Sendrecv(owned.data() + static_cast<int>(owned.size()) - 1, 1, MPI_DOUBLE, rank + 1, 12,
                     ghi.data(), 1, MPI_DOUBLE, rank + 1, 11, MPI_COMM_WORLD, &st);
    } else {
        ghi[0] = 0.0;
    }
}

}  // namespace

int num_ctrl_advance(std::vector<double>& owned, std::vector<double>& glo, std::vector<double>& ghi,
                     CtrlState& ctrl, HistRec& hist, const ProfKnobs& prof, double kappa, double dx,
                     int lo, int hi, int n_global, int rank, int nproc) {
    const double dt_max = adv_cfl_limit(kappa, dx, prof.cfl);
    const double grow = 1.1;
    const double shrink = 0.5;
    for (;;) {
        halo_exchange(owned, glo, ghi, rank, nproc);
        double dt_try = std::min(ctrl.last_dt * grow, dt_max);
        if (!(dt_try > 0.0)) {
            dt_try = adv_pick_dt(kappa, dx, prof.dt0, prof.cfl);
        }
        std::vector<double> trial;
        adv_ftcs_trial(owned, glo, ghi, kappa, dx, dt_try, lo, hi, n_global, trial);
        double local_du = adv_max_abs_delta(owned, trial);
        double max_du = 0.0;
        MPI_Allreduce(&local_du, &max_du, 1, MPI_DOUBLE, MPI_MAX, MPI_COMM_WORLD);
        const double scale = std::max(ctrl.accum, 1e-12);
        if (max_du <= prof.tol * scale) {
            owned.swap(trial);
            ctrl.last_dt = dt_try;
            ctrl.accum = 0.9 * ctrl.accum + 0.1 * max_du;
            ctrl.n_accept += 1;
            if (rank == 0) {
                hist.dt_seq.push_back(dt_try);
                hist.step += 1;
            }
            return 0;
        }
        ctrl.n_reject += 1;
        ctrl.last_dt = std::max(dt_try * shrink, dt_max * 1e-6);
    }
}

CtrlState num_ctrl_restore(const GlobRec& glob, const ProfKnobs& prof, double kappa, double dx) {
    (void)prof;
    (void)kappa;
    (void)dx;
    return glob.ctrl;
}
''')

# --- reduction: GID-order Kahan on rank0 ---
(root / "numerics/reduction.cpp").write_text(r'''#include "reduction.hpp"

#include "../core/advance.hpp"

#include <mpi.h>

#include <vector>

double num_mass_observe(const std::vector<double>& owned, double dx, int n_global, int rank,
                        int nproc) {
    int lo = 0, hi = 0, loc_n = 0;
    adv_decompose(n_global, nproc, rank, lo, hi, loc_n);
    std::vector<int> counts(static_cast<size_t>(nproc), 0);
    std::vector<int> displ(static_cast<size_t>(nproc), 0);
    for (int r = 0; r < nproc; ++r) {
        int rlo, rhi, rln;
        adv_decompose(n_global, nproc, r, rlo, rhi, rln);
        counts[static_cast<size_t>(r)] = rln;
        displ[static_cast<size_t>(r)] = rlo;
    }
    std::vector<double> global;
    if (rank == 0) {
        global.assign(static_cast<size_t>(n_global), 0.0);
    } else {
        global.assign(1, 0.0);
    }
    MPI_Gatherv(owned.data(), loc_n, MPI_DOUBLE, global.data(), counts.data(), displ.data(),
                MPI_DOUBLE, 0, MPI_COMM_WORLD);
    double mass = 0.0;
    if (rank == 0) {
        double sum = 0.0;
        double c = 0.0;
        for (double v : global) {
            const double y = v - c;
            const double t = sum + y;
            c = (t - sum) - y;
            sum = t;
        }
        mass = sum * dx;
    }
    MPI_Bcast(&mass, 1, MPI_DOUBLE, 0, MPI_COMM_WORLD);
    return mass;
}
''')

# --- publish: atomic rename + HistRec gating ---
(root / "storage/publish.cpp").write_text(r'''#include "publish.hpp"

#include "io.hpp"

#include <H5Cpp.h>
#include <cstdio>
#include <filesystem>
#include <fstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

namespace {

void write_dset(H5::Group& g, const char* name, const std::vector<double>& v) {
    hsize_t dims[1] = {static_cast<hsize_t>(v.size())};
    H5::DataSpace space(1, dims);
    H5::DataSet ds = g.createDataSet(name, H5::PredType::NATIVE_DOUBLE, space);
    if (!v.empty()) {
        ds.write(v.data(), H5::PredType::NATIVE_DOUBLE);
    }
}

void write_body(const std::string& path, const DistRec& dist, const HistRec& hist,
                const CtrlState& ctrl) {
    H5::H5File file(path, H5F_ACC_TRUNC);
    write_dset(file, "owned", dist.owned);
    H5::Group histg = file.createGroup("/hist");
    write_dset(histg, "dt_seq", hist.dt_seq);
    write_dset(histg, "mass_seq", hist.m_seq);
    int step = hist.step;
    histg.createAttribute("step", H5::PredType::NATIVE_INT, H5::DataSpace(H5S_SCALAR))
        .write(H5::PredType::NATIVE_INT, &step);
    H5::Group cg = file.createGroup("/ctrl");
    cg.createAttribute("last_dt", H5::PredType::NATIVE_DOUBLE, H5::DataSpace(H5S_SCALAR))
        .write(H5::PredType::NATIVE_DOUBLE, &ctrl.last_dt);
    cg.createAttribute("n_reject", H5::PredType::NATIVE_INT, H5::DataSpace(H5S_SCALAR))
        .write(H5::PredType::NATIVE_INT, &ctrl.n_reject);
    cg.createAttribute("n_accept", H5::PredType::NATIVE_INT, H5::DataSpace(H5S_SCALAR))
        .write(H5::PredType::NATIVE_INT, &ctrl.n_accept);
    cg.createAttribute("accum", H5::PredType::NATIVE_DOUBLE, H5::DataSpace(H5S_SCALAR))
        .write(H5::PredType::NATIVE_DOUBLE, &ctrl.accum);
}

}  // namespace

int stor_publish_final(const DistRec& dist, const HistRec& hist, const CtrlState& ctrl,
                       const Paths& paths) {
    fs::create_directories(paths.stage_dir);
    const std::string tmp = paths.stage_dir + "/final.publish.tmp.h5";
    if (stor_io::failpoint_is("before_publish_rename")) {
        write_body(tmp, dist, hist, ctrl);
        std::ofstream partial(paths.stage_dir + "/publish_partial.flag");
        partial << "1\n";
        std::remove(tmp.c_str());
        return 1;
    }
    write_body(tmp, dist, hist, ctrl);
    std::error_code ec;
    fs::rename(tmp, paths.final_h5, ec);
    if (ec) {
        fs::copy_file(tmp, paths.final_h5, fs::copy_options::overwrite_existing, ec);
        std::remove(tmp.c_str());
    }
    if (hist.step > 0 && !hist.dt_seq.empty() && !hist.m_seq.empty() &&
        static_cast<int>(hist.dt_seq.size()) == hist.step) {
        std::ofstream tally(paths.stage_dir + "/tally.txt", std::ios::app);
        tally << "step=" << hist.step << " n=" << dist.owned.size() << "\n";
    }
    return 0;
}
''')

# --- io: RDONLY input opens ---
io_path = root / "storage/io.cpp"
io_txt = io_path.read_text()
io_txt = io_txt.replace(
    """int open_flags_for_input() {
    return H5F_ACC_RDWR;
}""",
    """int open_flags_for_input() {
    return H5F_ACC_RDONLY;
}""",
)
io_path.write_text(io_txt)

# --- driver: fingerprint gate on continue ---
drv = (root / "core/driver.cpp").read_text()
old = """        try {
            gen = stor_catalog_select(bag);
            (void)bag.fingerprint_want;
        } catch (...) {
            sel_ok = 0;
        }"""
new = """        try {
            gen = stor_catalog_select(bag);
            if (!bag.fingerprint_want.empty() && !gen.fingerprint.empty() &&
                gen.fingerprint != bag.fingerprint_want) {
                sel_ok = 0;
            }
        } catch (...) {
            sel_ok = 0;
        }"""
if old not in drv:
    raise SystemExit("driver fingerprint patch site missing")
(root / "core/driver.cpp").write_text(drv.replace(old, new))
print("oracle patches applied")
PY

bash "${ENV_ROOT}/scripts/build_x7.sh"

# targeted smoke: one repartition + one failpoint publish
STAGE_SMOKE="/tmp/x7_oracle_smoke"
rm -rf "${STAGE_SMOKE}"
mkdir -p "${STAGE_SMOKE}"
BIN="${ENV_ROOT}/bin/x7_orch"
CFG="${ENV_ROOT}/cfg_store/cfg_sa.json"
PROF="${ENV_ROOT}/profiles/px.prof"

mpirun --allow-run-as-root --oversubscribe -np 5 "${BIN}" \
  --mode continuous --cfg "${CFG}" --profile "${PROF}" \
  --stage "${STAGE_SMOKE}/un" --final "${STAGE_SMOKE}/un/final.h5"

mpirun --allow-run-as-root --oversubscribe -np 2 "${BIN}" \
  --mode continuous --cfg "${CFG}" --profile "${PROF}" \
  --write-ckpt "${STAGE_SMOKE}/ckpt.h5" \
  --stage "${STAGE_SMOKE}/wr" --final "${STAGE_SMOKE}/wr/final.h5"

mpirun --allow-run-as-root --oversubscribe -np 5 "${BIN}" \
  --mode continue --cfg "${CFG}" --profile "${PROF}" \
  --ckpt "${STAGE_SMOKE}/ckpt.h5" \
  --stage "${STAGE_SMOKE}/co" --final "${STAGE_SMOKE}/co/final.h5"

X7_FAILPOINT=before_publish_rename mpirun --allow-run-as-root --oversubscribe -np 2 "${BIN}" \
  --mode continuous --cfg "${CFG}" --profile "${PROF}" \
  --stage "${STAGE_SMOKE}/fp" --final "${STAGE_SMOKE}/fp/final.h5" || true
test ! -f "${STAGE_SMOKE}/fp/final.h5"

bash "${ENV_ROOT}/h1/run_x7.sh"
