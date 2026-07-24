#include "io.hpp"

#include <H5Cpp.h>
#include <algorithm>
#include <cstdlib>
#include <cstdio>
#include <cstring>
#include <stdexcept>
#include <string>

namespace stor_io {
namespace {

void write_dset(H5::Group& g, const char* name, const std::vector<double>& v) {
    hsize_t dims[1] = {static_cast<hsize_t>(v.size())};
    H5::DataSpace space(1, dims);
    H5::DataSet ds = g.createDataSet(name, H5::PredType::NATIVE_DOUBLE, space);
    if (!v.empty()) {
        ds.write(v.data(), H5::PredType::NATIVE_DOUBLE);
    }
}

void write_dset_i(H5::Group& g, const char* name, const std::vector<int>& v) {
    hsize_t dims[1] = {static_cast<hsize_t>(v.size())};
    H5::DataSpace space(1, dims);
    H5::DataSet ds = g.createDataSet(name, H5::PredType::NATIVE_INT, space);
    if (!v.empty()) {
        ds.write(v.data(), H5::PredType::NATIVE_INT);
    }
}

void read_dset(H5::Group& g, const char* name, std::vector<double>& v) {
    H5::DataSet ds = g.openDataSet(name);
    H5::DataSpace space = ds.getSpace();
    hsize_t dims[1];
    space.getSimpleExtentDims(dims, nullptr);
    v.resize(static_cast<size_t>(dims[0]));
    if (!v.empty()) {
        ds.read(v.data(), H5::PredType::NATIVE_DOUBLE);
    }
}

void read_dset_i(H5::Group& g, const char* name, std::vector<int>& v) {
    H5::DataSet ds = g.openDataSet(name);
    H5::DataSpace space = ds.getSpace();
    hsize_t dims[1];
    space.getSimpleExtentDims(dims, nullptr);
    v.resize(static_cast<size_t>(dims[0]));
    if (!v.empty()) {
        ds.read(v.data(), H5::PredType::NATIVE_INT);
    }
}

int read_attr_i(H5::H5Object& loc, const char* name, int fallback) {
    if (loc.attrExists(name)) {
        H5::Attribute a = loc.openAttribute(name);
        int v = fallback;
        a.read(H5::PredType::NATIVE_INT, &v);
        return v;
    }
    return fallback;
}

double read_attr_d(H5::H5Object& loc, const char* name, double fallback) {
    if (loc.attrExists(name)) {
        H5::Attribute a = loc.openAttribute(name);
        double v = fallback;
        a.read(H5::PredType::NATIVE_DOUBLE, &v);
        return v;
    }
    return fallback;
}

std::string read_attr_s(H5::H5Object& loc, const char* name) {
    if (!loc.attrExists(name)) {
        return "";
    }
    H5::Attribute a = loc.openAttribute(name);
    H5::DataType dt = a.getDataType();
    if (dt.getClass() == H5T_STRING) {
        if (dt.isVariableStr()) {
            char* buf = nullptr;
            a.read(dt, &buf);
            std::string out = buf ? std::string(buf) : "";
            free(buf);
            return out;
        }
        const size_t n = dt.getSize();
        std::string s(n, '\0');
        a.read(dt, &s[0]);
        while (!s.empty() && s.back() == '\0') {
            s.pop_back();
        }
        return s;
    }
    return "";
}

void put_attr_i(H5::H5Object& loc, const char* name, int val) {
    if (loc.attrExists(name)) {
        loc.openAttribute(name).write(H5::PredType::NATIVE_INT, &val);
    } else {
        loc.createAttribute(name, H5::PredType::NATIVE_INT, H5::DataSpace(H5S_SCALAR))
            .write(H5::PredType::NATIVE_INT, &val);
    }
}

void put_attr_d(H5::H5Object& loc, const char* name, double val) {
    if (loc.attrExists(name)) {
        loc.openAttribute(name).write(H5::PredType::NATIVE_DOUBLE, &val);
    } else {
        loc.createAttribute(name, H5::PredType::NATIVE_DOUBLE, H5::DataSpace(H5S_SCALAR))
            .write(H5::PredType::NATIVE_DOUBLE, &val);
    }
}

void put_attr_s(H5::H5Object& loc, const char* name, const std::string& val) {
    if (loc.attrExists(name)) {
        loc.removeAttr(name);
    }
    H5::StrType st(H5::PredType::C_S1, val.size() + 1);
    st.setCset(H5T_CSET_ASCII);
    loc.createAttribute(name, st, H5::DataSpace(H5S_SCALAR)).write(st, val.c_str());
}

H5::Group open_or_create(H5::H5File& file, const std::string& path) {
    if (file.nameExists(path)) {
        return file.openGroup(path);
    }
    return file.createGroup(path);
}

}  // namespace

std::string gen_group_name(int id) {
    char buf[32];
    std::snprintf(buf, sizeof(buf), "gen_%04d", id);
    return std::string(buf);
}

std::string failpoint_token() {
    const char* e = std::getenv("X7_FAILPOINT");
    return e ? std::string(e) : std::string();
}

bool failpoint_is(const char* key) {
    const std::string tok = failpoint_token();
    if (tok == key) {
        return true;
    }
    if (tok.rfind(std::string(key) + ":", 0) == 0) {
        return true;
    }
    return false;
}

int failpoint_rank() {
    const std::string tok = failpoint_token();
    const std::string prefix = "after_rank_block:";
    if (tok.rfind(prefix, 0) != 0) {
        return -1;
    }
    return std::stoi(tok.substr(prefix.size()));
}

int open_flags_for_input() {
    return H5F_ACC_RDWR;
}

bool name_exists(const std::string& path, const std::string& obj) {
    try {
        H5::H5File file(path, H5F_ACC_RDONLY);
        return file.nameExists(obj);
    } catch (...) {
        return false;
    }
}

int layout_family(const std::string& path) {
    H5::H5File file(path, H5F_ACC_RDONLY);
    H5::Group root = file.openGroup("/");
    int max_layout = 0;
    for (hsize_t i = 0; i < root.getNumObjs(); ++i) {
        if (root.getObjTypeByIdx(i) != H5G_GROUP) {
            continue;
        }
        std::string n = root.getObjnameByIdx(i);
        if (n.rfind("gen_", 0) != 0) {
            continue;
        }
        H5::Group g = root.openGroup(n);
        int lv = read_attr_i(g, "layout", 2);
        max_layout = std::max(max_layout, lv);
    }
    if (max_layout > 0) {
        return max_layout;
    }
    if (file.attrExists("layout")) {
        return read_attr_i(file, "layout", 1);
    }
    if (file.nameExists("owned_r0")) {
        return 1;
    }
    return 0;
}

int list_gen_ids(const std::string& path, std::vector<int>& ids) {
    ids.clear();
    H5::H5File file(path, H5F_ACC_RDONLY);
    H5::Group root = file.openGroup("/");
    for (hsize_t i = 0; i < root.getNumObjs(); ++i) {
        if (root.getObjTypeByIdx(i) != H5G_GROUP) {
            continue;
        }
        std::string n = root.getObjnameByIdx(i);
        if (n.rfind("gen_", 0) != 0) {
            continue;
        }
        ids.push_back(std::stoi(n.substr(4)));
    }
    if (ids.empty() && (file.nameExists("owned_r0") || read_attr_i(file, "layout", 0) == 1)) {
        ids.push_back(read_attr_i(file, "gen_id", 1));
    }
    std::sort(ids.begin(), ids.end());
    return 0;
}

int read_gen_meta(const std::string& path, const std::string& group_path, GenRec& out) {
    H5::H5File file(path, open_flags_for_input());
    out.store_path = path;
    out.group_path = group_path;
    if (group_path.empty() || group_path == "/") {
        out.layout_ver = 1;
        out.id = read_attr_i(file, "gen_id", 1);
        out.step = read_attr_i(file, "step", 0);
        out.nproc_write = read_attr_i(file, "nproc_write", 1);
        out.marker = read_attr_i(file, "committed", 0);
        out.fingerprint = read_attr_s(file, "fingerprint");
        out.field_cksum = read_attr_d(file, "field_cksum", 0.0);
        if (open_flags_for_input() == H5F_ACC_RDWR) {
            H5::Group root = file.openGroup("/");
            put_attr_i(root, "access_epoch", read_attr_i(root, "access_epoch", 0) + 1);
        }
        return 0;
    }
    H5::Group g = file.openGroup(group_path);
    out.layout_ver = read_attr_i(g, "layout", 2);
    out.id = read_attr_i(g, "gen_id", 0);
    out.step = read_attr_i(g, "step", 0);
    out.nproc_write = read_attr_i(g, "nproc_write", 1);
    out.marker = read_attr_i(g, "committed", 0);
    out.fingerprint = read_attr_s(g, "fingerprint");
    out.field_cksum = read_attr_d(g, "field_cksum", 0.0);
    if (open_flags_for_input() == H5F_ACC_RDWR) {
        put_attr_i(g, "access_epoch", read_attr_i(g, "access_epoch", 0) + 1);
    }
    return 0;
}

int read_rank_block(const std::string& path, const GenRec& gen, int rank, std::vector<double>& owned,
                    std::vector<double>& glo, std::vector<double>& ghi, std::vector<int>& gids) {
    H5::H5File file(path, H5F_ACC_RDONLY);
    if (gen.layout_ver == 1) {
        char ob[32], lb[32], hb[32], gb[32];
        std::snprintf(ob, sizeof(ob), "owned_r%d", rank);
        std::snprintf(lb, sizeof(lb), "ghost_lo_r%d", rank);
        std::snprintf(hb, sizeof(hb), "ghost_hi_r%d", rank);
        std::snprintf(gb, sizeof(gb), "gids_r%d", rank);
        read_dset(file, ob, owned);
        read_dset(file, lb, glo);
        read_dset(file, hb, ghi);
        read_dset_i(file, gb, gids);
        return 0;
    }
    H5::Group g = file.openGroup(gen.group_path);
    char pfx[32];
    std::snprintf(pfx, sizeof(pfx), "r%d", rank);
    read_dset(g, (std::string(pfx) + "_owned").c_str(), owned);
    read_dset(g, (std::string(pfx) + "_ghost_lo").c_str(), glo);
    read_dset(g, (std::string(pfx) + "_ghost_hi").c_str(), ghi);
    read_dset_i(g, (std::string(pfx) + "_gids").c_str(), gids);
    return 0;
}

int read_hist(const std::string& path, const GenRec& gen, HistRec& out) {
    H5::H5File file(path, H5F_ACC_RDONLY);
    std::string hist_path = "/hist";
    if (gen.layout_ver >= 3) {
        hist_path = gen.group_path + "/hist";
    }
    if (!file.nameExists(hist_path)) {
        out.dt_seq.clear();
        out.m_seq.clear();
        out.step = 0;
        return 0;
    }
    H5::Group hist = file.openGroup(hist_path);
    read_dset(hist, "dt_seq", out.dt_seq);
    read_dset(hist, "mass_seq", out.m_seq);
    out.step = read_attr_i(hist, "step", static_cast<int>(out.dt_seq.size()));
    return 0;
}

int read_ctrl(const std::string& path, const GenRec& gen, CtrlState& out) {
    out = CtrlState{0.0, 0, 0, 1.0};
    H5::H5File file(path, H5F_ACC_RDONLY);
    std::string ctrl_path = "/ctrl";
    if (gen.layout_ver >= 3) {
        ctrl_path = gen.group_path + "/ctrl";
    } else if (gen.layout_ver == 1) {
        if (file.attrExists("ctrl_last_dt")) {
            out.last_dt = read_attr_d(file, "ctrl_last_dt", out.last_dt);
            out.n_reject = read_attr_i(file, "ctrl_n_reject", 0);
            out.n_accept = read_attr_i(file, "ctrl_n_accept", 0);
            out.accum = read_attr_d(file, "ctrl_accum", 1.0);
            return 0;
        }
        return 0;
    }
    if (!file.nameExists(ctrl_path)) {
        return 0;
    }
    H5::Group c = file.openGroup(ctrl_path);
    out.last_dt = read_attr_d(c, "last_dt", 0.0);
    out.n_reject = read_attr_i(c, "n_reject", 0);
    out.n_accept = read_attr_i(c, "n_accept", 0);
    out.accum = read_attr_d(c, "accum", 1.0);
    return 0;
}

int write_gen_begin(const std::string& path, int gen_id, int step, int nproc, int layout_ver,
                    const std::string& fingerprint) {
    unsigned flags = H5F_ACC_RDWR;
    {
        FILE* probe = std::fopen(path.c_str(), "rb");
        if (probe == nullptr) {
            flags = H5F_ACC_TRUNC;
        } else {
            std::fclose(probe);
        }
    }
    H5::H5File file(path, flags);
    std::string gn = std::string("/") + gen_group_name(gen_id);
    H5::Group g = open_or_create(file, gn);
    put_attr_i(g, "gen_id", gen_id);
    put_attr_i(g, "step", step);
    put_attr_i(g, "nproc_write", nproc);
    put_attr_i(g, "layout", layout_ver);
    put_attr_i(g, "committed", 0);
    put_attr_s(g, "fingerprint", fingerprint);
    return 0;
}

int write_rank_block(const std::string& path, int gen_id, int rank, const std::vector<double>& owned,
                     const std::vector<double>& glo, const std::vector<double>& ghi,
                     const std::vector<int>& gids) {
    H5::H5File file(path, H5F_ACC_RDWR);
    H5::Group g = file.openGroup(std::string("/") + gen_group_name(gen_id));
    char pfx[32];
    std::snprintf(pfx, sizeof(pfx), "r%d", rank);
    auto put = [&](const char* suffix, auto& vec, auto pred) {
        std::string nm = std::string(pfx) + suffix;
        if (g.nameExists(nm)) {
            g.unlink(nm);
        }
        hsize_t dims[1] = {static_cast<hsize_t>(vec.size())};
        H5::DataSpace space(1, dims);
        H5::DataSet ds = g.createDataSet(nm.c_str(), pred, space);
        if (!vec.empty()) {
            ds.write(vec.data(), pred);
        }
    };
    put("_owned", owned, H5::PredType::NATIVE_DOUBLE);
    put("_ghost_lo", glo, H5::PredType::NATIVE_DOUBLE);
    put("_ghost_hi", ghi, H5::PredType::NATIVE_DOUBLE);
    put("_gids", gids, H5::PredType::NATIVE_INT);
    return 0;
}

int write_hist_ctrl(const std::string& path, int gen_id, int layout_ver, const HistRec& hist,
                    const CtrlState& ctrl, double field_cksum) {
    H5::H5File file(path, H5F_ACC_RDWR);
    std::string base = std::string("/") + gen_group_name(gen_id);
    H5::Group g = file.openGroup(base);
    put_attr_d(g, "field_cksum", field_cksum);

    std::string hist_path = (layout_ver >= 3) ? (base + "/hist") : "/hist";
    std::string ctrl_path = (layout_ver >= 3) ? (base + "/ctrl") : "/ctrl";

    if (file.nameExists(hist_path)) {
        file.unlink(hist_path);
    }
    H5::Group histg = file.createGroup(hist_path);
    write_dset(histg, "dt_seq", hist.dt_seq);
    write_dset(histg, "mass_seq", hist.m_seq);
    put_attr_i(histg, "step", hist.step);

    if (file.nameExists(ctrl_path)) {
        file.unlink(ctrl_path);
    }
    H5::Group cg = file.createGroup(ctrl_path);
    put_attr_d(cg, "last_dt", ctrl.last_dt);
    put_attr_i(cg, "n_reject", ctrl.n_reject);
    put_attr_i(cg, "n_accept", ctrl.n_accept);
    put_attr_d(cg, "accum", ctrl.accum);
    return 0;
}

int write_commit(const std::string& path, int gen_id, int committed) {
    H5::H5File file(path, H5F_ACC_RDWR);
    H5::Group g = file.openGroup(std::string("/") + gen_group_name(gen_id));
    put_attr_i(g, "committed", committed);
    return 0;
}

}  // namespace stor_io
