#pragma once

#include <cstdint>
#include <string>
#include <vector>

struct CtrlState {
    double last_dt;
    int n_reject;
    int n_accept;
    double accum;
};

struct Bag {
    std::string store_path;
    std::string fingerprint_want;
    int n_global;
};

struct GenRec {
    int id;
    int step;
    int nproc_write;
    int layout_ver;
    std::string store_path;
    std::string group_path;
    int marker;
    std::string fingerprint;
    double field_cksum;
};

struct PartMap {
    int nproc;
    int rank;
};

struct GlobRec {
    int ncell;
    int step;
    std::vector<double> vals;
    std::vector<int> gids;
    CtrlState ctrl;
    std::vector<double> dt_seq;
    std::vector<double> m_seq;
};

struct DistRec {
    int rank;
    int nproc;
    int step;
    double dx;
    std::vector<double> owned;
    std::vector<double> ghost_lo;
    std::vector<double> ghost_hi;
    std::vector<int> gids;
};

struct HistRec {
    int step;
    std::vector<double> dt_seq;
    std::vector<double> m_seq;
};

struct ArtRec {
    std::string out_h5;
    std::string stage_dir;
    int step;
};

struct Paths {
    std::string final_h5;
    std::string stage_dir;
    std::string ckpt_path;
};

struct RunCfg {
    int n_global;
    int until_step;
    int ckpt_step;
    double kappa_scale;
    int seed;
    std::string tag;
};

struct ProfKnobs {
    double kappa;
    double dt0;
    double cfl;
    double tol;
};
