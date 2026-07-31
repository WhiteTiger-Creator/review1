#!/bin/bash
# Read the brief, look at what the levels do, then write a level book that
# takes the readings which act together, lets the reach level off, and chases
# the middle of the levels rather than their average, because the spikes only
# ever go one way. Measure on the dev split before trusting it.
set -euo pipefail

# Made here rather than leaned on: a runner that is not root can only write
# these because the image sets their mode as the tree is copied in. Setting it
# on the directory alone is not enough, since overwriting a file that is
# already there needs write permission on the file.
mkdir -p /app/src /app/build /app/output

sed -n '1,80p' /app/docs/BRIEF.md >/dev/null

cat > /app/src/sedgemere.cpp <<'SEDGEMERE_CPP_EOF'
// Fits the sedgemere levels: the readings that act together, the reach that
// levels off, and a fit that chases the middle of the levels rather than
// their average, because the spikes only ever go one way.
#include <algorithm>
#include <cmath>
#include <cstdlib>
#include <fstream>
#include <sstream>
#include <string>
#include <vector>

namespace {

const int BINS = 10;

std::vector<std::vector<double>> readRows(const std::string &path,
                                          bool withLevel,
                                          std::vector<double> *levels) {
    std::vector<std::vector<double>> rows;
    std::ifstream in(path);
    std::string line;
    bool first = true;
    while (std::getline(in, line)) {
        if (line.empty()) continue;
        if (first) { first = false; continue; }
        std::vector<double> cells;
        std::stringstream row(line);
        std::string cell;
        while (std::getline(row, cell, ',')) cells.push_back(std::atof(cell.c_str()));
        if (withLevel) {
            levels->push_back(cells.back());
            cells.pop_back();
        }
        rows.push_back(cells);
    }
    return rows;
}

// reed silt brack fen moss gale sluice weir, then what they do together
std::vector<double> design(const std::vector<double> &x,
                           const std::vector<double> &cuts) {
    std::vector<double> f;
    f.push_back(1.0);
    for (double v : x) f.push_back(v);
    // which two readings pull together is named by the weir
    f.push_back(x[7] > 0.5 ? x[2] * x[4] : x[0] * x[1]);
    f.push_back((x[6] > 0.5 ? 1.0 : -1.0) * x[4]);  // moss, signed by sluice
    for (double c : cuts) f.push_back(x[3] >= c ? 1.0 : 0.0);  // fen, levelling
    return f;
}

bool solveNormal(std::vector<std::vector<double>> A, std::vector<double> &out) {
    int k = (int)A.size();
    for (int col = 0; col < k; col++) {
        int piv = col;
        for (int r = col; r < k; r++)
            if (std::fabs(A[r][col]) > std::fabs(A[piv][col])) piv = r;
        std::swap(A[col], A[piv]);
        double pv = A[col][col];
        if (std::fabs(pv) < 1e-12) return false;
        for (int q = col; q <= k; q++) A[col][q] /= pv;
        for (int r = 0; r < k; r++) {
            if (r == col || A[r][col] == 0.0) continue;
            double fct = A[r][col];
            for (int q = col; q <= k; q++) A[r][q] -= fct * A[col][q];
        }
    }
    out.resize(k);
    for (int p = 0; p < k; p++) out[p] = A[p][k];
    return true;
}

std::vector<double> weightedFit(const std::vector<std::vector<double>> &X,
                                const std::vector<double> &y,
                                const std::vector<double> &w) {
    int k = (int)X[0].size();
    std::vector<std::vector<double>> A(k, std::vector<double>(k + 1, 0.0));
    for (size_t i = 0; i < X.size(); i++) {
        for (int p = 0; p < k; p++) {
            double wp = w[i] * X[i][p];
            for (int q = p; q < k; q++) A[p][q] += wp * X[i][q];
            A[p][k] += wp * y[i];
        }
    }
    for (int p = 0; p < k; p++)
        for (int q = 0; q < p; q++) A[p][q] = A[q][p];
    for (int p = 0; p < k; p++) A[p][p] += 1e-6;
    std::vector<double> out;
    if (!solveNormal(A, out)) out.assign(k, 0.0);
    return out;
}

}  // namespace

int main(int argc, char **argv) {
    if (argc != 3) return 2;
    std::vector<double> levels;
    std::vector<std::vector<double>> train =
        readRows("/app/data/train.csv", true, &levels);
    if (train.empty()) return 1;

    std::vector<double> fen;
    for (const auto &r : train) fen.push_back(r[3]);
    std::sort(fen.begin(), fen.end());
    std::vector<double> cuts;
    for (int q = 1; q < BINS; q++)
        cuts.push_back(fen[(size_t)((double)fen.size() * q / BINS)]);

    std::vector<std::vector<double>> X;
    X.reserve(train.size());
    for (const auto &r : train) X.push_back(design(r, cuts));

    // Least squares once, then chase the middle: reweighting by one over the
    // size of each miss turns the same machinery into an absolute-error fit,
    // which is what the levels are scored by and what the one-sided spikes
    // demand.
    std::vector<double> w(X.size(), 1.0);
    std::vector<double> beta = weightedFit(X, levels, w);
    for (int pass = 0; pass < 60; pass++) {
        for (size_t i = 0; i < X.size(); i++) {
            double fit = 0.0;
            for (size_t j = 0; j < beta.size(); j++) fit += beta[j] * X[i][j];
            w[i] = 1.0 / std::max(0.02, std::fabs(fit - levels[i]));
        }
        beta = weightedFit(X, levels, w);
    }

    std::vector<std::vector<double>> ask = readRows(argv[1], false, nullptr);
    std::ofstream out(argv[2]);
    out.setf(std::ios::fixed);
    out.precision(6);
    for (const auto &r : ask) {
        std::vector<double> f = design(r, cuts);
        double v = 0.0;
        for (size_t j = 0; j < beta.size(); j++) v += beta[j] * f[j];
        out << v << "\n";
    }
    return 0;
}
SEDGEMERE_CPP_EOF

g++ -O2 -std=c++17 -o /app/build/sedgemere /app/src/*.cpp

# Read the dev split back, as a check that it runs.
/app/build/sedgemere /app/data/dev.csv /app/output/levels.txt
