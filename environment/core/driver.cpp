#include "../numerics/controller.hpp"
#include "../numerics/reduction.hpp"
#include "../restart/partition.hpp"
#include "../restart/reconstruct.hpp"
#include "../storage/catalog.hpp"
#include "../storage/io.hpp"
#include "../storage/layout.hpp"
#include "../storage/publish.hpp"
#include "../storage/validate.hpp"
#include "advance.hpp"
#include "types.hpp"

#include <mpi.h>

#include <cstdio>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <string>
#include <vector>
#include <algorithm>

namespace fs = std::filesystem;

std::string arg_val(int argc, char** argv, const char* key, const std::string& fallback) {
    for (int i = 1; i + 1 < argc; ++i) {
        if (std::string(argv[i]) == key) {
            return argv[i + 1];
        }
    }
    return fallback;
}

RunCfg load_cfg(const std::string& path) {
    RunCfg c{};
    std::ifstream in(path);
    std::string txt((std::istreambuf_iterator<char>(in)), std::istreambuf_iterator<char>());
    auto grab = [&](const char* key, int& out) {
        const std::string k = std::string("\"") + key + "\"";
        auto p = txt.find(k);
        if (p == std::string::npos) {
            return;
        }
        p = txt.find(':', p);
        if (p == std::string::npos) {
            return;
        }
        out = std::stoi(txt.substr(p + 1));
    };
    auto grabd = [&](const char* key, double& out) {
        const std::string k = std::string("\"") + key + "\"";
        auto p = txt.find(k);
        if (p == std::string::npos) {
            return;
        }
        p = txt.find(':', p);
        if (p == std::string::npos) {
            return;
        }
        out = std::stod(txt.substr(p + 1));
    };
    auto grabs = [&](const char* key, std::string& out) {
        const std::string k = std::string("\"") + key + "\"";
        auto p = txt.find(k);
        if (p == std::string::npos) {
            return;
        }
        p = txt.find('"', p + k.size());
        if (p == std::string::npos) {
            return;
        }
        auto q = txt.find('"', p + 1);
        out = txt.substr(p + 1, q - p - 1);
    };
    grab("n_global", c.n_global);
    grab("until_step", c.until_step);
    grab("ckpt_step", c.ckpt_step);
    grabd("kappa_scale", c.kappa_scale);
    grab("seed", c.seed);
    grabs("tag", c.tag);
    return c;
}

ProfKnobs load_prof(const std::string& path) {
    ProfKnobs p{0.4, 0.002, 0.4, 1e-3};
    std::ifstream in(path);
    std::string line;
    while (std::getline(in, line)) {
        if (line.empty() || line[0] == '#') {
            continue;
        }
        auto eq = line.find('=');
        if (eq == std::string::npos) {
            continue;
        }
        const std::string k = line.substr(0, eq);
        const std::string v = line.substr(eq + 1);
        if (k == "KAPPA") {
            p.kappa = std::stod(v);
        } else if (k == "DT0") {
            p.dt0 = std::stod(v);
        } else if (k == "CFL") {
            p.cfl = std::stod(v);
        } else if (k == "TOL") {
            p.tol = std::stod(v);
        }
    }
    return p;
}

void resolve_group_path(GenRec& gen) {
    char gp[64];
    if (gen.layout_ver == 1 && !stor_io::name_exists(gen.store_path, "/gen_0001") &&
        !stor_io::name_exists(gen.store_path, "/" + stor_io::gen_group_name(gen.id))) {
        gen.group_path = "/";
        return;
    }
    std::snprintf(gp, sizeof(gp), "/gen_%04d", gen.id);
    gen.group_path = gp;
    if (!stor_io::name_exists(gen.store_path, gen.group_path) && gen.layout_ver == 1) {
        gen.group_path = "/";
    }
}

void gather_global(const RunCfg& cfg, int rank, int nproc, const std::vector<double>& owned,
                   const std::vector<int>& gids, std::vector<double>& global) {
    const int loc_n = static_cast<int>(owned.size());
    std::vector<int> counts(static_cast<size_t>(nproc), 0);
    std::vector<int> displ(static_cast<size_t>(nproc), 0);
    MPI_Allgather(&loc_n, 1, MPI_INT, counts.data(), 1, MPI_INT, MPI_COMM_WORLD);
    for (int r = 1; r < nproc; ++r) {
        displ[static_cast<size_t>(r)] = displ[static_cast<size_t>(r - 1)] + counts[static_cast<size_t>(r - 1)];
    }
    const int total = displ[static_cast<size_t>(nproc - 1)] + counts[static_cast<size_t>(nproc - 1)];
    std::vector<double> flat(static_cast<size_t>(rank == 0 ? std::max(total, 1) : 1), 0.0);
    std::vector<int> flat_g(static_cast<size_t>(rank == 0 ? std::max(total, 1) : 1), 0);
    MPI_Gatherv(owned.data(), loc_n, MPI_DOUBLE, flat.data(), counts.data(), displ.data(), MPI_DOUBLE,
                0, MPI_COMM_WORLD);
    MPI_Gatherv(gids.data(), loc_n, MPI_INT, flat_g.data(), counts.data(), displ.data(), MPI_INT, 0,
                MPI_COMM_WORLD);
    if (rank == 0) {
        global.assign(static_cast<size_t>(cfg.n_global), 0.0);
        for (int i = 0; i < total; ++i) {
            const int g = flat_g[static_cast<size_t>(i)];
            if (g >= 0 && g < cfg.n_global) {
                global[static_cast<size_t>(g)] = flat[static_cast<size_t>(i)];
            }
        }
    }
}

int write_checkpoint(const RunCfg& cfg, const ProfKnobs& prof, int rank, int nproc, int step,
                     const std::string& ckpt_out, const std::vector<double>& owned,
                     const std::vector<double>& glo, const std::vector<double>& ghi,
                     const std::vector<int>& gids, const HistRec& hist, const CtrlState& ctrl,
                     const std::vector<double>& global_rank0) {
    const int layout_ver = 3;
    const std::string fp = adv_fingerprint(cfg, prof);
    const int gen_id = 1;
    if (rank == 0) {
        std::remove(ckpt_out.c_str());
        stor_io::write_gen_begin(ckpt_out, gen_id, step, nproc, layout_ver, fp);
    }
    MPI_Barrier(MPI_COMM_WORLD);
    const int fp_rank = stor_io::failpoint_rank();
    for (int wr = 0; wr < nproc; ++wr) {
        if (rank == wr) {
            stor_io::write_rank_block(ckpt_out, gen_id, rank, owned, glo, ghi, gids);
        }
        MPI_Barrier(MPI_COMM_WORLD);
        if (fp_rank >= 0 && wr == fp_rank) {
            return 1;
        }
    }
    if (stor_io::failpoint_is("after_history") || stor_io::failpoint_is("before_commit")) {
        if (rank == 0) {
            double ck = adv_field_cksum(global_rank0);
            stor_io::write_hist_ctrl(ckpt_out, gen_id, layout_ver, hist, ctrl, ck);
        }
        MPI_Barrier(MPI_COMM_WORLD);
        return 1;
    }
    if (rank == 0) {
        double ck = adv_field_cksum(global_rank0);
        stor_io::write_hist_ctrl(ckpt_out, gen_id, layout_ver, hist, ctrl, ck);
        stor_io::write_commit(ckpt_out, gen_id, 1);
    }
    MPI_Barrier(MPI_COMM_WORLD);
    return 0;
}

int run_continuous(const RunCfg& cfg, const ProfKnobs& prof, int rank, int nproc,
                   const std::string& ckpt_out, const Paths& paths) {
    const double dx = adv_dx(cfg.n_global);
    const double kappa = prof.kappa * cfg.kappa_scale;
    int lo = 0, hi = 0, loc_n = 0;
    adv_decompose(cfg.n_global, nproc, rank, lo, hi, loc_n);

    std::vector<double> global;
    if (rank == 0) {
        adv_init_bump(cfg.n_global, cfg.seed, global);
    }
    global.resize(static_cast<size_t>(cfg.n_global));
    MPI_Bcast(global.data(), cfg.n_global, MPI_DOUBLE, 0, MPI_COMM_WORLD);

    std::vector<double> owned, glo, ghi;
    std::vector<int> gids;
    adv_extract_local(global, lo, hi, cfg.n_global, owned, glo, ghi, gids);

    HistRec hist{};
    hist.step = 0;
    CtrlState ctrl = num_ctrl_defaults(prof, kappa, dx);

    for (int accepted = 0; accepted < cfg.until_step;) {
        num_ctrl_advance(owned, glo, ghi, ctrl, hist, prof, kappa, dx, lo, hi, cfg.n_global, rank,
                         nproc);
        ++accepted;
        const double mass = num_mass_observe(owned, dx, cfg.n_global, rank, nproc);
        if (rank == 0) {
            hist.m_seq.push_back(mass);
        }
        gather_global(cfg, rank, nproc, owned, gids, global);
        if (accepted == cfg.ckpt_step && !ckpt_out.empty()) {
            const int wrc = write_checkpoint(cfg, prof, rank, nproc, accepted, ckpt_out, owned, glo, ghi,
                                             gids, hist, ctrl, global);
            if (wrc != 0) {
                return wrc;
            }
        }
    }

    gather_global(cfg, rank, nproc, owned, gids, global);
    int pub_rc = 0;
    if (rank == 0) {
        DistRec dist{};
        dist.step = hist.step;
        dist.dx = dx;
        dist.owned = global;
        dist.ghost_lo = {0.0};
        dist.ghost_hi = {0.0};
        dist.gids.resize(global.size());
        for (size_t i = 0; i < global.size(); ++i) {
            dist.gids[i] = static_cast<int>(i);
        }
        fs::create_directories(paths.stage_dir);
        pub_rc = stor_publish_final(dist, hist, ctrl, paths);
    }
    MPI_Bcast(&pub_rc, 1, MPI_INT, 0, MPI_COMM_WORLD);
    return pub_rc;
}

int run_continue(const RunCfg& cfg, const ProfKnobs& prof, int rank, int nproc,
                 const std::string& ckpt_in, const Paths& paths) {
    Bag bag{};
    bag.store_path = ckpt_in;
    bag.n_global = cfg.n_global;
    bag.fingerprint_want = adv_fingerprint(cfg, prof);

    GenRec gen{};
    int sel_ok = 1;
    if (rank == 0) {
        try {
            gen = stor_catalog_select(bag);
            (void)bag.fingerprint_want;
        } catch (...) {
            sel_ok = 0;
        }
    }
    MPI_Bcast(&sel_ok, 1, MPI_INT, 0, MPI_COMM_WORLD);
    if (!sel_ok) {
        return 3;
    }
    MPI_Bcast(&gen.id, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&gen.step, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&gen.nproc_write, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&gen.layout_ver, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&gen.marker, 1, MPI_INT, 0, MPI_COMM_WORLD);
    gen.store_path = ckpt_in;
    if (rank == 0) {
        stor_layout::load_meta(ckpt_in, gen.id, gen);
        gen.store_path = ckpt_in;
    }
    resolve_group_path(gen);

    GlobRec glob{};
    if (rank == 0) {
        glob = restart_reconstruct(gen, bag);
    }
    glob.ncell = cfg.n_global;
    MPI_Bcast(&glob.step, 1, MPI_INT, 0, MPI_COMM_WORLD);
    glob.vals.resize(static_cast<size_t>(cfg.n_global));
    MPI_Bcast(glob.vals.data(), cfg.n_global, MPI_DOUBLE, 0, MPI_COMM_WORLD);

    int ndt = 0, nms = 0;
    if (rank == 0) {
        ndt = static_cast<int>(glob.dt_seq.size());
        nms = static_cast<int>(glob.m_seq.size());
    }
    MPI_Bcast(&ndt, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&nms, 1, MPI_INT, 0, MPI_COMM_WORLD);
    glob.dt_seq.resize(static_cast<size_t>(ndt));
    glob.m_seq.resize(static_cast<size_t>(nms));
    if (ndt > 0) {
        MPI_Bcast(glob.dt_seq.data(), ndt, MPI_DOUBLE, 0, MPI_COMM_WORLD);
    }
    if (nms > 0) {
        MPI_Bcast(glob.m_seq.data(), nms, MPI_DOUBLE, 0, MPI_COMM_WORLD);
    }
    MPI_Bcast(&glob.ctrl.last_dt, 1, MPI_DOUBLE, 0, MPI_COMM_WORLD);
    MPI_Bcast(&glob.ctrl.n_reject, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&glob.ctrl.n_accept, 1, MPI_INT, 0, MPI_COMM_WORLD);
    MPI_Bcast(&glob.ctrl.accum, 1, MPI_DOUBLE, 0, MPI_COMM_WORLD);

    DistRec dist = restart_partition(glob, nproc, rank);
    const double dx = adv_dx(cfg.n_global);
    const double kappa = prof.kappa * cfg.kappa_scale;
    int lo = dist.gids.empty() ? 0 : dist.gids.front();
    int hi = dist.gids.empty() ? -1 : dist.gids.back();

    HistRec hist{};
    hist.step = glob.step;
    hist.dt_seq = glob.dt_seq;
    hist.m_seq = glob.m_seq;
    CtrlState ctrl = num_ctrl_restore(glob, prof, kappa, dx);

    for (int step = glob.step; step < cfg.until_step;) {
        num_ctrl_advance(dist.owned, dist.ghost_lo, dist.ghost_hi, ctrl, hist, prof, kappa, dx, lo,
                         hi, cfg.n_global, rank, nproc);
        ++step;
        const double mass = num_mass_observe(dist.owned, dx, cfg.n_global, rank, nproc);
        if (rank == 0) {
            hist.m_seq.push_back(mass);
        }
        dist.step = step;
    }

    std::vector<double> gfin;
    gather_global(cfg, rank, nproc, dist.owned, dist.gids, gfin);
    int pub_rc = 0;
    if (rank == 0) {
        DistRec out{};
        out.step = hist.step;
        out.dx = dx;
        out.owned = gfin;
        out.ghost_lo = {0.0};
        out.ghost_hi = {0.0};
        out.gids.resize(gfin.size());
        for (size_t i = 0; i < gfin.size(); ++i) {
            out.gids[i] = static_cast<int>(i);
        }
        fs::create_directories(paths.stage_dir);
        pub_rc = stor_publish_final(out, hist, ctrl, paths);
        std::ofstream meta(paths.stage_dir + "/picked.json");
        meta << "{\"gen_id\":" << gen.id << ",\"marker\":" << gen.marker
             << ",\"layout_ver\":" << gen.layout_ver << "}";
    }
    MPI_Bcast(&pub_rc, 1, MPI_INT, 0, MPI_COMM_WORLD);
    return pub_rc;
}

int main(int argc, char** argv) {
    MPI_Init(&argc, &argv);
    int rank = 0, nproc = 1;
    MPI_Comm_rank(MPI_COMM_WORLD, &rank);
    MPI_Comm_size(MPI_COMM_WORLD, &nproc);

    const std::string mode = arg_val(argc, argv, "--mode", "continuous");
    const std::string cfg_path = arg_val(argc, argv, "--cfg", "");
    const std::string prof_path = arg_val(argc, argv, "--profile", "");
    const std::string ckpt = arg_val(argc, argv, "--ckpt", "");
    const std::string ckpt_out = arg_val(argc, argv, "--write-ckpt", "");
    const std::string stage = arg_val(argc, argv, "--stage", "/app/output/stage");
    const std::string final_h5 = arg_val(argc, argv, "--final", "/app/output/final.h5");

    if (cfg_path.empty() || prof_path.empty()) {
        if (rank == 0) {
            std::cerr << "usage: x7_orch --mode continuous|continue --cfg C --profile P\n";
        }
        MPI_Finalize();
        return 2;
    }

    RunCfg cfg = load_cfg(cfg_path);
    ProfKnobs prof = load_prof(prof_path);
    Paths paths{};
    paths.final_h5 = final_h5;
    paths.stage_dir = stage;
    paths.ckpt_path = ckpt;

    int rc = 0;
    if (mode == "continue") {
        rc = run_continue(cfg, prof, rank, nproc, ckpt, paths);
    } else {
        rc = run_continuous(cfg, prof, rank, nproc, ckpt_out, paths);
    }

    MPI_Finalize();
    return rc;
}
