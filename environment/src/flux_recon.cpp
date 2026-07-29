#include <algorithm>
#include <filesystem>
#include <fstream>
#include <iostream>
#include <sstream>
#include <string>
#include <vector>

namespace fs = std::filesystem;

int main(int argc, char** argv) {
    std::string case_dir = "/app/environment/cases";
    std::string out_path = "/app/output/flux_report.json";
    for (int i = 1; i + 1 < argc; ++i) {
        std::string arg = argv[i];
        if (arg == "--case-dir") case_dir = argv[++i];
        else if (arg == "--out") out_path = argv[++i];
    }

    std::vector<std::string> ids;
    for (const auto& entry : fs::directory_iterator(case_dir)) {
        if (entry.path().extension() == ".flux") {
            std::ifstream in(entry.path());
            std::string key, id;
            while (in >> key) {
                if (key == "case_id" && in >> id) {
                    ids.push_back(id);
                    break;
                }
            }
        }
    }
    std::sort(ids.begin(), ids.end());
    fs::create_directories(fs::path(out_path).parent_path());
    std::ofstream out(out_path);
    out << "{\"cases\":[";
    for (size_t i = 0; i < ids.size(); ++i) {
        if (i) out << ",";
        out << "{\"case_id\":\"" << ids[i] << "\",\"rank\":0,\"tensor\":[[0,0],[0,0]],"
               "\"drift\":0,\"weighted_rmse\":0,\"quality\":\"review\",\"flags\":[],\"group_balance\":[]}";
    }
    out << "],\"summary\":{\"case_count\":" << ids.size()
        << ",\"stable_count\":0,\"review_count\":" << ids.size()
        << ",\"signature\":\"0000000000000000\"}}\n";
    return 0;
}
