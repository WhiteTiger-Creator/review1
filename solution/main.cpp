#include <algorithm>
#include <array>
#include <iostream>
#include <map>
#include <set>
#include <vector>

using I = __int128_t;
const long long HASH_MOD = 1000000007LL;
const long long HASH_BASE = 1000003LL;
struct P { long long x[4]; };
I det4(I a[4][4]) {
    I result = 0;
    for (int col = 0; col < 4; ++col) {
        I m[3][3];
        for (int r = 1; r < 4; ++r) { int c2 = 0; for (int c = 0; c < 4; ++c) if (c != col) m[r - 1][c2++] = a[r][c]; }
        I minor = m[0][0] * (m[1][1] * m[2][2] - m[1][2] * m[2][1]) - m[0][1] * (m[1][0] * m[2][2] - m[1][2] * m[2][0]) + m[0][2] * (m[1][0] * m[2][1] - m[1][1] * m[2][0]);
        result += (col % 2 ? -1 : 1) * a[0][col] * minor;
    }
    return result;
}
I orient(const P& a, const P& b, const P& c, const P& d, const P& q) {
    I m[4][4]; const P* base[4] = {&b, &c, &d, &q};
    for (int r = 0; r < 4; ++r) for (int j = 0; j < 4; ++j) m[r][j] = I(base[r]->x[j]) - a.x[j];
    return det4(m);
}
I gcd_i(I a, I b) {
    if (a < 0) a = -a;
    if (b < 0) b = -b;
    while (b != 0) {
        I r = a % b;
        a = b;
        b = r;
    }
    return a;
}
std::array<I, 5> hyperplane(const std::vector<P>& p, const std::array<int, 4>& ids) {
    I rows[4][5];
    for (int r = 0; r < 4; ++r) {
        for (int c = 0; c < 4; ++c) rows[r][c] = p[ids[r]].x[c];
        rows[r][4] = 1;
    }
    std::array<I, 5> coeff{};
    for (int col = 0; col < 5; ++col) {
        I sub[4][4];
        for (int r = 0; r < 4; ++r) {
            int c2 = 0;
            for (int c = 0; c < 5; ++c) if (c != col) sub[r][c2++] = rows[r][c];
        }
        coeff[col] = (col % 2 ? -1 : 1) * det4(sub);
    }
    return coeff;
}
I eval_plane(const std::array<I, 5>& coeff, const P& point) {
    I value = coeff[4];
    for (int i = 0; i < 4; ++i) value += coeff[i] * point.x[i];
    return value;
}
bool primitive_carrier(const std::vector<P>& p, const std::array<int, 4>& ids, std::array<I, 5>& coeff) {
    coeff = hyperplane(p, ids);
    bool positive = false, negative = false;
    for (const auto& point : p) {
        I value = eval_plane(coeff, point);
        positive |= value > 0;
        negative |= value < 0;
    }
    if (!positive && !negative) return false;
    if (positive && negative) return false;
    if (negative) for (auto& value : coeff) value = -value;
    I scale = 0;
    for (I value : coeff) scale = gcd_i(scale, value);
    for (auto& value : coeff) value /= scale;
    return true;
}
long long residue(I value) {
    value %= HASH_MOD;
    if (value < 0) value += HASH_MOD;
    return (long long)value;
}
long long append_hash(long long h, long long value) {
    value %= HASH_MOD;
    if (value < 0) value += HASH_MOD;
    return (h * HASH_BASE + value) % HASH_MOD;
}
long long append_hash_i(long long h, I value) {
    return (h * HASH_BASE + residue(value)) % HASH_MOD;
}

I det_small(const std::vector<std::vector<I>>& matrix) {
    if (matrix.size() == 1) return matrix[0][0];
    I result = 0;
    for (int col = 0; col < (int)matrix.size(); ++col) {
        std::vector<std::vector<I>> minor;
        for (int row = 1; row < (int)matrix.size(); ++row) {
            std::vector<I> reduced;
            for (int column = 0; column < (int)matrix.size(); ++column) {
                if (column != col) reduced.push_back(matrix[row][column]);
            }
            minor.push_back(std::move(reduced));
        }
        I term = matrix[0][col] * det_small(minor);
        result += (col % 2 == 0 ? term : -term);
    }
    return result;
}

int affine_dimension(const std::vector<P>& points, const std::vector<int>& ids) {
    if (ids.size() <= 1) return 0;
    std::vector<std::array<I, 4>> differences;
    for (int index = 1; index < (int)ids.size(); ++index) {
        std::array<I, 4> row{};
        for (int axis = 0; axis < 4; ++axis) {
            row[axis] = I(points[ids[index]].x[axis]) - points[ids[0]].x[axis];
        }
        differences.push_back(row);
    }
    for (int rank = std::min(4, (int)differences.size()); rank >= 1; --rank) {
        std::vector<int> row_choice(rank);
        auto choose_rows = [&](auto&& self, int depth, int start) -> bool {
            if (depth == rank) {
                std::vector<int> column_choice(rank);
                auto choose_columns = [&](auto&& column_self, int column_depth, int column_start) -> bool {
                    if (column_depth == rank) {
                        std::vector<std::vector<I>> matrix(
                            rank, std::vector<I>(rank)
                        );
                        for (int r = 0; r < rank; ++r) {
                            for (int c = 0; c < rank; ++c) {
                                matrix[r][c] =
                                    differences[row_choice[r]][column_choice[c]];
                            }
                        }
                        return det_small(matrix) != 0;
                    }
                    for (int column = column_start; column <= 4 - (rank - column_depth); ++column) {
                        column_choice[column_depth] = column;
                        if (column_self(column_self, column_depth + 1, column + 1)) {
                            return true;
                        }
                    }
                    return false;
                };
                return choose_columns(choose_columns, 0, 0);
            }
            for (int row = start; row <= (int)differences.size() - (rank - depth); ++row) {
                row_choice[depth] = row;
                if (self(self, depth + 1, row + 1)) return true;
            }
            return false;
        };
        if (choose_rows(choose_rows, 0, 0)) return rank;
    }
    return 0;
}

bool strict_subset(const std::vector<int>& lower, const std::vector<int>& upper) {
    return lower.size() < upper.size() &&
           std::includes(upper.begin(), upper.end(), lower.begin(), lower.end());
}

int main() {
    std::ios::sync_with_stdio(false); std::cin.tie(nullptr);
    int n; if (!(std::cin >> n)) return 1;
    std::vector<P> p(n); for (auto& q : p) for (long long& x : q.x) std::cin >> x;
    std::map<std::vector<int>, std::array<I, 5>> facets;
    for (int i = 0; i < n; ++i) for (int j = i + 1; j < n; ++j) for (int k = j + 1; k < n; ++k) for (int l = k + 1; l < n; ++l) {
        std::array<I, 5> coeff{};
        if (!primitive_carrier(p, {i, j, k, l}, coeff)) continue;
        std::vector<int> ids;
        for (int q = 0; q < n; ++q) if (eval_plane(coeff, p[q]) == 0) ids.push_back(q);
        if (ids.size() >= 4 && !facets.count(ids)) facets[ids] = coeff;
    }
    std::set<int> hull;
    for (const auto& [f, coeff] : facets) hull.insert(f.begin(), f.end());
    std::cout << "HULL " << hull.size(); for (int x : hull) std::cout << ' ' << x + 1; std::cout << '\n';
    std::cout << "FACETS " << facets.size() << '\n';
    for (const auto& [f, coeff] : facets) { std::cout << "FACET " << f.size(); for (int x : f) std::cout << ' ' << x + 1; std::cout << '\n'; }
    long long facet_hash = 17;
    for (const auto& [f, coeff] : facets) {
        facet_hash = append_hash(facet_hash, (long long)f.size());
        for (int x : f) facet_hash = append_hash(facet_hash, x + 1);
    }
    std::vector<int> hull_ids(hull.begin(), hull.end());
    long long triple_face_hash = 31;
    for (int a = 0; a < (int)hull_ids.size(); ++a) {
        for (int b = a + 1; b < (int)hull_ids.size(); ++b) {
            for (int c = b + 1; c < (int)hull_ids.size(); ++c) {
                int count = 0;
                for (const auto& [f, coeff] : facets) {
                    if (std::binary_search(f.begin(), f.end(), hull_ids[a]) &&
                        std::binary_search(f.begin(), f.end(), hull_ids[b]) &&
                        std::binary_search(f.begin(), f.end(), hull_ids[c])) ++count;
                }
                triple_face_hash = append_hash(triple_face_hash, hull_ids[a] + 1);
                triple_face_hash = append_hash(triple_face_hash, hull_ids[b] + 1);
                triple_face_hash = append_hash(triple_face_hash, hull_ids[c] + 1);
                triple_face_hash = append_hash(triple_face_hash, count);
            }
        }
    }
    long long normal_hash = 43;
    for (const auto& [f, coeff] : facets) {
        normal_hash = append_hash(normal_hash, (long long)f.size());
        for (int x : f) normal_hash = append_hash(normal_hash, x + 1);
        for (I value : coeff) normal_hash = append_hash_i(normal_hash, value);
    }
    std::vector<std::pair<std::vector<int>, std::array<I, 5>>> ordered_facets(
        facets.begin(), facets.end()
    );
    long long pair_normal_hash = 83;
    for (int left = 0; left < (int)ordered_facets.size(); ++left) {
        for (int right = left + 1; right < (int)ordered_facets.size(); ++right) {
            std::vector<int> face;
            std::set_intersection(
                ordered_facets[left].first.begin(), ordered_facets[left].first.end(),
                ordered_facets[right].first.begin(), ordered_facets[right].first.end(),
                std::back_inserter(face)
            );
            if (face.size() < 2) continue;
            pair_normal_hash = append_hash(pair_normal_hash, left + 1);
            pair_normal_hash = append_hash(pair_normal_hash, right + 1);
            pair_normal_hash = append_hash(pair_normal_hash, (long long)face.size());
            for (int x : face) pair_normal_hash = append_hash(pair_normal_hash, x + 1);
            for (I value : ordered_facets[left].second) {
                pair_normal_hash = append_hash_i(pair_normal_hash, value);
            }
            for (I value : ordered_facets[right].second) {
                pair_normal_hash = append_hash_i(pair_normal_hash, value);
            }
        }
    }
    std::set<std::vector<int>> intersections;
    for (auto left = facets.begin(); left != facets.end(); ++left) {
        auto right = left;
        ++right;
        for (; right != facets.end(); ++right) {
            std::vector<int> face;
            std::set_intersection(
                left->first.begin(), left->first.end(),
                right->first.begin(), right->first.end(),
                std::back_inserter(face)
            );
            if (face.size() >= 2) intersections.insert(face);
        }
    }
    long long intersection_hash = 59;
    for (const auto& face : intersections) {
        int containing = 0;
        for (const auto& [f, coeff] : facets) {
            bool has_all = true;
            for (int vertex : face) {
                if (!std::binary_search(f.begin(), f.end(), vertex)) {
                    has_all = false;
                    break;
                }
            }
            if (has_all) ++containing;
        }
        intersection_hash = append_hash(intersection_hash, (long long)face.size());
        for (int x : face) intersection_hash = append_hash(intersection_hash, x + 1);
        intersection_hash = append_hash(intersection_hash, containing);
    }
    long long carrier_sign_hash = 71;
    for (int i = 0; i < n; ++i) {
        for (int j = i + 1; j < n; ++j) {
            for (int k = j + 1; k < n; ++k) {
                for (int l = k + 1; l < n; ++l) {
                    std::array<I, 5> coeff = hyperplane(p, {i, j, k, l});
                    bool any_coeff = false;
                    for (I value : coeff) any_coeff |= value != 0;
                    if (!any_coeff) continue;
                    std::vector<I> values;
                    values.reserve(n);
                    I first_nonzero = 0;
                    for (const auto& point : p) {
                        I value = eval_plane(coeff, point);
                        values.push_back(value);
                        if (first_nonzero == 0 && value != 0) first_nonzero = value;
                    }
                    if (first_nonzero == 0) continue;
                    if (first_nonzero < 0) {
                        for (I& value : values) value = -value;
                    }
                    for (int id : {i, j, k, l}) carrier_sign_hash = append_hash(carrier_sign_hash, id + 1);
                    for (I value : values) {
                        int sign_code = value < 0 ? 0 : (value == 0 ? 1 : 2);
                        carrier_sign_hash = append_hash(carrier_sign_hash, sign_code);
                    }
                }
            }
        }
    }
    long long vertex_figure_hash = 97;
    for (int vertex : hull) {
        std::vector<int> incident;
        for (int index = 0; index < (int)ordered_facets.size(); ++index) {
            const auto& facet = ordered_facets[index].first;
            if (std::binary_search(facet.begin(), facet.end(), vertex)) {
                incident.push_back(index + 1);
            }
        }
        vertex_figure_hash = append_hash(vertex_figure_hash, vertex + 1);
        vertex_figure_hash = append_hash(vertex_figure_hash, (long long)incident.size());
        for (int position : incident) vertex_figure_hash = append_hash(vertex_figure_hash, position);
        for (int a = 0; a < (int)incident.size(); ++a) {
            for (int b = a + 1; b < (int)incident.size(); ++b) {
                int left = incident[a] - 1;
                int right = incident[b] - 1;
                std::vector<int> face;
                std::set_intersection(
                    ordered_facets[left].first.begin(), ordered_facets[left].first.end(),
                    ordered_facets[right].first.begin(), ordered_facets[right].first.end(),
                    std::back_inserter(face)
                );
                vertex_figure_hash = append_hash(vertex_figure_hash, incident[a]);
                vertex_figure_hash = append_hash(vertex_figure_hash, incident[b]);
                vertex_figure_hash = append_hash(vertex_figure_hash, (long long)face.size());
                for (int x : face) vertex_figure_hash = append_hash(vertex_figure_hash, x + 1);
            }
        }
    }
    long long facet_triple_hash = 109;
    for (int a = 0; a < (int)ordered_facets.size(); ++a) {
        for (int b = a + 1; b < (int)ordered_facets.size(); ++b) {
            for (int c = b + 1; c < (int)ordered_facets.size(); ++c) {
                std::vector<int> first;
                std::set_intersection(
                    ordered_facets[a].first.begin(), ordered_facets[a].first.end(),
                    ordered_facets[b].first.begin(), ordered_facets[b].first.end(),
                    std::back_inserter(first)
                );
                std::vector<int> face;
                std::set_intersection(
                    first.begin(), first.end(),
                    ordered_facets[c].first.begin(), ordered_facets[c].first.end(),
                    std::back_inserter(face)
                );
                if (face.empty()) continue;
                int containing = 0;
                for (const auto& [f, coeff] : facets) {
                    bool has_all = true;
                    for (int vertex : face) {
                        if (!std::binary_search(f.begin(), f.end(), vertex)) {
                            has_all = false;
                            break;
                        }
                    }
                    if (has_all) ++containing;
                }
                facet_triple_hash = append_hash(facet_triple_hash, a + 1);
                facet_triple_hash = append_hash(facet_triple_hash, b + 1);
                facet_triple_hash = append_hash(facet_triple_hash, c + 1);
                facet_triple_hash = append_hash(facet_triple_hash, (long long)face.size());
                for (int x : face) facet_triple_hash = append_hash(facet_triple_hash, x + 1);
                facet_triple_hash = append_hash(facet_triple_hash, containing);
            }
        }
    }
    long long facet_quad_hash = 127;
    for (int a = 0; a < (int)ordered_facets.size(); ++a) {
        for (int b = a + 1; b < (int)ordered_facets.size(); ++b) {
            for (int c = b + 1; c < (int)ordered_facets.size(); ++c) {
                for (int d = c + 1; d < (int)ordered_facets.size(); ++d) {
                    std::vector<int> first;
                    std::set_intersection(
                        ordered_facets[a].first.begin(), ordered_facets[a].first.end(),
                        ordered_facets[b].first.begin(), ordered_facets[b].first.end(),
                        std::back_inserter(first)
                    );
                    std::vector<int> second;
                    std::set_intersection(
                        first.begin(), first.end(),
                        ordered_facets[c].first.begin(), ordered_facets[c].first.end(),
                        std::back_inserter(second)
                    );
                    std::vector<int> face;
                    std::set_intersection(
                        second.begin(), second.end(),
                        ordered_facets[d].first.begin(), ordered_facets[d].first.end(),
                        std::back_inserter(face)
                    );
                    if (face.empty()) continue;
                    int containing = 0;
                    for (const auto& [f, coeff] : facets) {
                        bool has_all = true;
                        for (int vertex : face) {
                            if (!std::binary_search(f.begin(), f.end(), vertex)) {
                                has_all = false;
                                break;
                            }
                        }
                        if (has_all) ++containing;
                    }
                    facet_quad_hash = append_hash(facet_quad_hash, a + 1);
                    facet_quad_hash = append_hash(facet_quad_hash, b + 1);
                    facet_quad_hash = append_hash(facet_quad_hash, c + 1);
                    facet_quad_hash = append_hash(facet_quad_hash, d + 1);
                    facet_quad_hash = append_hash(facet_quad_hash, (long long)face.size());
                    for (int x : face) facet_quad_hash = append_hash(facet_quad_hash, x + 1);
                    facet_quad_hash = append_hash(facet_quad_hash, containing);
                }
            }
        }
    }
    std::set<std::vector<int>> all_faces;
    if (!ordered_facets.empty()) {
        all_faces.insert(hull_ids);
        for (const auto& facet : ordered_facets) all_faces.insert(facet.first);
        bool changed = true;
        while (changed) {
            changed = false;
            std::vector<std::vector<int>> snapshot(all_faces.begin(), all_faces.end());
            for (int left = 0; left < (int)snapshot.size(); ++left) {
                for (int right = left + 1; right < (int)snapshot.size(); ++right) {
                    std::vector<int> face;
                    std::set_intersection(
                        snapshot[left].begin(), snapshot[left].end(),
                        snapshot[right].begin(), snapshot[right].end(),
                        std::back_inserter(face)
                    );
                    if (!face.empty() && all_faces.insert(face).second) changed = true;
                }
            }
        }
    }
    struct FaceInfo {
        std::vector<int> ids;
        int dimension;
    };
    std::vector<FaceInfo> face_family;
    for (const auto& face : all_faces) {
        face_family.push_back({face, affine_dimension(p, face)});
    }
    std::sort(
        face_family.begin(), face_family.end(),
        [](const FaceInfo& left, const FaceInfo& right) {
            if (left.dimension != right.dimension) {
                return left.dimension < right.dimension;
            }
            return left.ids < right.ids;
        }
    );
    long long face_lattice_hash = 149;
    for (const auto& face : face_family) {
        int containing = 0;
        for (const auto& facet : ordered_facets) {
            if (std::includes(
                    facet.first.begin(), facet.first.end(),
                    face.ids.begin(), face.ids.end()
                )) {
                ++containing;
            }
        }
        face_lattice_hash = append_hash(face_lattice_hash, face.dimension);
        face_lattice_hash = append_hash(
            face_lattice_hash, (long long)face.ids.size()
        );
        for (int vertex : face.ids) {
            face_lattice_hash = append_hash(face_lattice_hash, vertex + 1);
        }
        face_lattice_hash = append_hash(face_lattice_hash, containing);
    }
    std::array<std::vector<int>, 4> positions_by_dimension;
    for (int position = 0; position < (int)face_family.size(); ++position) {
        int dimension = face_family[position].dimension;
        if (0 <= dimension && dimension <= 3) {
            positions_by_dimension[dimension].push_back(position);
        }
    }
    long long flag_hash = 163;
    for (int p0 : positions_by_dimension[0]) {
        for (int p1 : positions_by_dimension[1]) {
            if (!strict_subset(face_family[p0].ids, face_family[p1].ids)) continue;
            for (int p2 : positions_by_dimension[2]) {
                if (!strict_subset(face_family[p1].ids, face_family[p2].ids)) continue;
                for (int p3 : positions_by_dimension[3]) {
                    if (!strict_subset(face_family[p2].ids, face_family[p3].ids)) continue;
                    flag_hash = append_hash(flag_hash, p0 + 1);
                    flag_hash = append_hash(flag_hash, p1 + 1);
                    flag_hash = append_hash(flag_hash, p2 + 1);
                    flag_hash = append_hash(flag_hash, p3 + 1);
                }
            }
        }
    }
    long long facet_carrier_hash = 181;
    for (int position = 0; position < (int)ordered_facets.size(); ++position) {
        const auto& facet = ordered_facets[position].first;
        const auto& normal = ordered_facets[position].second;
        facet_carrier_hash = append_hash(facet_carrier_hash, position + 1);
        facet_carrier_hash = append_hash(
            facet_carrier_hash, (long long)facet.size()
        );
        for (int vertex : facet) {
            facet_carrier_hash = append_hash(facet_carrier_hash, vertex + 1);
        }
        for (I value : normal) {
            facet_carrier_hash = append_hash_i(facet_carrier_hash, value);
        }
        for (int a = 0; a < (int)facet.size(); ++a) {
            for (int b = a + 1; b < (int)facet.size(); ++b) {
                for (int c = b + 1; c < (int)facet.size(); ++c) {
                    for (int d = c + 1; d < (int)facet.size(); ++d) {
                        std::array<int, 4> ids{
                            facet[a], facet[b], facet[c], facet[d]
                        };
                        for (int id : ids) {
                            facet_carrier_hash = append_hash(
                                facet_carrier_hash, id + 1
                            );
                        }
                        std::array<I, 5> carrier = hyperplane(p, ids);
                        I scale = 0;
                        for (I value : carrier) scale = gcd_i(scale, value);
                        if (scale == 0) {
                            facet_carrier_hash = append_hash(
                                facet_carrier_hash, 0
                            );
                            continue;
                        }
                        for (I& value : carrier) value /= scale;
                        int pivot = 0;
                        while (normal[pivot] == 0) ++pivot;
                        if ((carrier[pivot] < 0) != (normal[pivot] < 0)) {
                            for (I& value : carrier) value = -value;
                        }
                        facet_carrier_hash = append_hash(
                            facet_carrier_hash, 1
                        );
                        for (I value : carrier) {
                            facet_carrier_hash = append_hash_i(
                                facet_carrier_hash, value
                            );
                        }
                    }
                }
            }
        }
    }
    std::map<std::vector<int>, int> face_positions;
    for (int position = 0; position < (int)face_family.size(); ++position) {
        face_positions[face_family[position].ids] = position + 1;
    }
    std::map<std::vector<int>, std::vector<int>> containing_cache;
    auto containing_facets = [&](const std::vector<int>& face)
        -> const std::vector<int>& {
        auto [iterator, inserted] = containing_cache.emplace(
            face, std::vector<int>{}
        );
        if (inserted) {
            for (
                int position = 0;
                position < (int)ordered_facets.size();
                ++position
            ) {
                if (std::includes(
                        ordered_facets[position].first.begin(),
                        ordered_facets[position].first.end(),
                        face.begin(), face.end()
                    )) {
                    iterator->second.push_back(position + 1);
                }
            }
        }
        return iterator->second;
    };
    long long face_normal_hash = 191;
    for (int position = 0; position < (int)face_family.size(); ++position) {
        const auto& face = face_family[position];
        std::vector<int> containing = containing_facets(face.ids);
        face_normal_hash = append_hash(face_normal_hash, position + 1);
        face_normal_hash = append_hash(face_normal_hash, face.dimension);
        face_normal_hash = append_hash(
            face_normal_hash, (long long)face.ids.size()
        );
        for (int vertex : face.ids) {
            face_normal_hash = append_hash(face_normal_hash, vertex + 1);
        }
        face_normal_hash = append_hash(
            face_normal_hash, (long long)containing.size()
        );
        for (int facet_position : containing) {
            face_normal_hash = append_hash(
                face_normal_hash, facet_position
            );
        }
        for (int facet_position : containing) {
            for (I value : ordered_facets[facet_position - 1].second) {
                face_normal_hash = append_hash_i(face_normal_hash, value);
            }
        }
    }
    long long normal_gram_hash = 193;
    for (int left = 0; left < (int)ordered_facets.size(); ++left) {
        for (int right = left + 1; right < (int)ordered_facets.size(); ++right) {
            std::vector<int> face;
            std::set_intersection(
                ordered_facets[left].first.begin(),
                ordered_facets[left].first.end(),
                ordered_facets[right].first.begin(),
                ordered_facets[right].first.end(),
                std::back_inserter(face)
            );
            if (face.empty()) continue;
            I left_norm = 0;
            I right_norm = 0;
            I inner = 0;
            for (int axis = 0; axis < 4; ++axis) {
                I left_value = ordered_facets[left].second[axis];
                I right_value = ordered_facets[right].second[axis];
                left_norm += left_value * left_value;
                right_norm += right_value * right_value;
                inner += left_value * right_value;
            }
            long long left_residue = residue(left_norm);
            long long right_residue = residue(right_norm);
            long long inner_residue = residue(inner);
            long long gram_residue = (
                left_residue * right_residue -
                inner_residue * inner_residue
            ) % HASH_MOD;
            if (gram_residue < 0) gram_residue += HASH_MOD;
            normal_gram_hash = append_hash(normal_gram_hash, left + 1);
            normal_gram_hash = append_hash(normal_gram_hash, right + 1);
            normal_gram_hash = append_hash(
                normal_gram_hash, face_positions.at(face)
            );
            normal_gram_hash = append_hash(
                normal_gram_hash, (long long)face.size()
            );
            for (int vertex : face) {
                normal_gram_hash = append_hash(
                    normal_gram_hash, vertex + 1
                );
            }
            normal_gram_hash = append_hash_i(normal_gram_hash, left_norm);
            normal_gram_hash = append_hash_i(normal_gram_hash, right_norm);
            normal_gram_hash = append_hash_i(normal_gram_hash, inner);
            normal_gram_hash = append_hash(
                normal_gram_hash, gram_residue
            );
        }
    }
    std::map<std::vector<int>, int> facet_positions;
    for (int position = 0; position < (int)ordered_facets.size(); ++position) {
        facet_positions[ordered_facets[position].first] = position + 1;
    }
    long long flag_normal_hash = 197;
    for (int p0 : positions_by_dimension[0]) {
        for (int p1 : positions_by_dimension[1]) {
            if (!strict_subset(face_family[p0].ids, face_family[p1].ids)) continue;
            for (int p2 : positions_by_dimension[2]) {
                if (!strict_subset(face_family[p1].ids, face_family[p2].ids)) continue;
                for (int p3 : positions_by_dimension[3]) {
                    if (!strict_subset(
                            face_family[p2].ids, face_family[p3].ids
                        )) {
                        continue;
                    }
                    int facet_position = facet_positions.at(
                        face_family[p3].ids
                    );
                    for (int position : {p0, p1, p2, p3}) {
                        flag_normal_hash = append_hash(
                            flag_normal_hash, position + 1
                        );
                    }
                    flag_normal_hash = append_hash(
                        flag_normal_hash, facet_position
                    );
                    for (I value : ordered_facets[facet_position - 1].second) {
                        flag_normal_hash = append_hash_i(
                            flag_normal_hash, value
                        );
                    }
                    for (int position : {p0, p1, p2}) {
                        flag_normal_hash = append_hash(
                            flag_normal_hash,
                            (long long)containing_facets(
                                face_family[position].ids
                            ).size()
                        );
                    }
                }
            }
        }
    }
    std::cout << "FACET_HASH " << facet_hash << '\n';
    std::cout << "TRIPLE_FACE_HASH " << triple_face_hash << '\n';
    std::cout << "NORMAL_HASH " << normal_hash << '\n';
    std::cout << "PAIR_NORMAL_HASH " << pair_normal_hash << '\n';
    std::cout << "INTERSECTION_HASH " << intersection_hash << '\n';
    std::cout << "CARRIER_SIGN_HASH " << carrier_sign_hash << '\n';
    std::cout << "VERTEX_FIGURE_HASH " << vertex_figure_hash << '\n';
    std::cout << "FACET_TRIPLE_HASH " << facet_triple_hash << '\n';
    std::cout << "FACET_QUAD_HASH " << facet_quad_hash << '\n';
    std::cout << "FACE_LATTICE_HASH " << face_lattice_hash << '\n';
    std::cout << "FLAG_HASH " << flag_hash << '\n';
    std::cout << "FACET_CARRIER_HASH " << facet_carrier_hash << '\n';
    std::cout << "FACE_NORMAL_HASH " << face_normal_hash << '\n';
    std::cout << "NORMAL_GRAM_HASH " << normal_gram_hash << '\n';
    std::cout << "FLAG_NORMAL_HASH " << flag_normal_hash << '\n';
}
