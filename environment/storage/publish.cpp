#include "publish.hpp"

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
    const std::string target = paths.final_h5;
    if (stor_io::failpoint_is("before_publish_rename")) {
        write_body(target, dist, hist, ctrl);
        std::ofstream partial(paths.stage_dir + "/publish_partial.flag");
        partial << "1\n";
        return 1;
    }
    write_body(target, dist, hist, ctrl);
    std::ofstream tally(paths.stage_dir + "/tally.txt", std::ios::app);
    tally << "step=" << hist.step << " n=" << dist.owned.size() << "\n";
    return 0;
}
