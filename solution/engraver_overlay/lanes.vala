namespace Kiln {
    public class Lanes {
        static int tier_distance (Bundle b, string tier) throws Error {
            var by_name = new HashTable<string, TierRow> (str_hash, str_equal);
            for (int i = 0; i < b.tiers.length; i++) {
                by_name[b.tiers[i].release_tier] = b.tiers[i];
            }
            if (!by_name.contains (tier)) {
                throw new InconsistentError.BAD_SET ("unknown tier");
            }
            int dist = 0;
            string cur = tier;
            var seen = new HashTable<string, bool> (str_hash, str_equal);
            while (true) {
                if (seen.contains (cur)) {
                    throw new InconsistentError.BAD_SET ("tier cycle");
                }
                seen[cur] = true;
                var row = by_name[cur];
                if (row.predecessor_tier == "") {
                    return dist;
                }
                if (!by_name.contains (row.predecessor_tier)) {
                    throw new InconsistentError.BAD_SET ("bad predecessor");
                }
                cur = row.predecessor_tier;
                dist++;
                if (dist > 64) {
                    throw new InconsistentError.BAD_SET ("tier depth");
                }
            }
        }

        static int tier_priority (Bundle b, string tier) throws Error {
            for (int i = 0; i < b.tiers.length; i++) {
                if (b.tiers[i].release_tier == tier) {
                    return b.tiers[i].tier_priority;
                }
            }
            throw new InconsistentError.BAD_SET ("tier priority missing");
        }

        static NoticeRow notice_for (Bundle b, string crate_id) throws Error {
            NoticeRow? found = null;
            for (int i = 0; i < b.notices.length; i++) {
                if (b.notices[i].crate_id == crate_id) {
                    if (found != null) {
                        throw new InconsistentError.BAD_SET ("dup notice");
                    }
                    found = b.notices[i];
                }
            }
            if (found == null) {
                throw new InconsistentError.BAD_SET ("missing notice");
            }
            return found;
        }

        static void resolve_notice (
            Bundle b,
            CrateAsm asm,
            HashTable<string, CrateAsm> by_id,
            HashTable<string, bool> visiting
        ) throws Error {
            if (asm.notice_resolved) {
                return;
            }
            var n = notice_for (b, asm.crate.crate_id);
            asm.notice_priority = n.notice_priority;
            asm.local_public = n.public_text;
            if (n.inherited_from == "") {
                asm.effective_fence = n.notice_fence;
                asm.effective_public = n.public_text;
                asm.root_seal_token = asm.crate.seal_token;
                asm.notice_resolved = true;
                return;
            }
            if (visiting.contains (asm.crate.crate_id)) {
                throw new InconsistentError.BAD_SET ("notice cycle");
            }
            visiting[asm.crate.crate_id] = true;
            if (!by_id.contains (n.inherited_from)) {
                throw new InconsistentError.BAD_SET ("bad inherit");
            }
            var parent = by_id[n.inherited_from];
            resolve_notice (b, parent, by_id, visiting);
            asm.effective_fence = parent.effective_fence;
            asm.root_seal_token = parent.root_seal_token;
            // Root-to-leaf: parent composed public + "#" + local.
            asm.effective_public = parent.effective_public + "#" + n.public_text;
            if (n.notice_fence != "" && n.notice_fence != asm.effective_fence) {
                throw new InconsistentError.BAD_SET ("inherit fence mismatch");
            }
            asm.notice_resolved = true;
            visiting.remove (asm.crate.crate_id);
        }

        static void elect_family_stamps (Bundle b) throws Error {
            var stamp_pri = new HashTable<string, int> (str_hash, str_equal);
            for (int i = 0; i < b.stamps.length; i++) {
                stamp_pri[b.stamps[i].stamp] = b.stamps[i].stamp_priority;
            }

            // family -> best (stamp_priority, notice_priority, stamp)
            var best_pri = new HashTable<string, int> (str_hash, str_equal);
            var best_notice_pri = new HashTable<string, int> (str_hash, str_equal);
            var best_stamp = new HashTable<string, string> (str_hash, str_equal);

            for (int i = 0; i < b.assemblies.length; i++) {
                var asm = b.assemblies[i];
                var c = asm.crate;
                if (c.compression_stamp == "vala_exit") {
                    continue;
                }
                int pri = stamp_pri[c.compression_stamp];
                int np = asm.notice_priority;
                string fam = c.family;
                if (!best_pri.contains (fam)) {
                    best_pri[fam] = pri;
                    best_notice_pri[fam] = np;
                    best_stamp[fam] = c.compression_stamp;
                    continue;
                }
                int cur_pri = best_pri[fam];
                int cur_np = best_notice_pri[fam];
                string cur_s = best_stamp[fam];
                bool better = false;
                if (pri > cur_pri) {
                    better = true;
                } else if (pri == cur_pri && np < cur_np) {
                    better = true;
                } else if (pri == cur_pri && np == cur_np
                           && strcmp (c.compression_stamp, cur_s) < 0) {
                    better = true;
                }
                if (better) {
                    best_pri[fam] = pri;
                    best_notice_pri[fam] = np;
                    best_stamp[fam] = c.compression_stamp;
                }
            }

            for (int i = 0; i < b.assemblies.length; i++) {
                var asm = b.assemblies[i];
                if (!best_stamp.contains (asm.crate.family)) {
                    throw new InconsistentError.BAD_SET ("no family stamp");
                }
                asm.index_note = best_stamp[asm.crate.family];
            }
        }

        static int ancestor_own_sum (CrateAsm asm, HashTable<string, CrateAsm> by_id, Bundle b) throws Error {
            int sum = 0;
            string fam = asm.crate.family;
            var n = notice_for (b, asm.crate.crate_id);
            string cur = n.inherited_from;
            var seen = new HashTable<string, bool> (str_hash, str_equal);
            while (cur != "") {
                if (seen.contains (cur)) {
                    throw new InconsistentError.BAD_SET ("ancestor cycle");
                }
                seen[cur] = true;
                if (!by_id.contains (cur)) {
                    throw new InconsistentError.BAD_SET ("missing ancestor");
                }
                var parent = by_id[cur];
                if (parent.crate.family == fam) {
                    sum += parent.byte_total;
                }
                cur = notice_for (b, parent.crate.crate_id).inherited_from;
            }
            return sum;
        }

        public static void resolve_notices_and_lanes (Bundle b) throws Error {
            var by_id = new HashTable<string, CrateAsm> (str_hash, str_equal);
            for (int i = 0; i < b.assemblies.length; i++) {
                by_id[b.assemblies[i].crate.crate_id] = b.assemblies[i];
            }

            var visiting = new HashTable<string, bool> (str_hash, str_equal);
            for (int i = 0; i < b.assemblies.length; i++) {
                resolve_notice (b, b.assemblies[i], by_id, visiting);
            }

            elect_family_stamps (b);

            var family_fence = new HashTable<string, string> (str_hash, str_equal);
            var alpha_by_family = new HashTable<string, ChecksumRow> (str_hash, str_equal);
            for (int i = 0; i < b.checksums.length; i++) {
                var a = b.checksums[i];
                if (alpha_by_family.contains (a.alphabet_id)) {
                    throw new InconsistentError.BAD_SET ("dup alphabet");
                }
                alpha_by_family[a.alphabet_id] = a;
            }

            for (int i = 0; i < b.assemblies.length; i++) {
                var asm = b.assemblies[i];
                if (asm.local_public == "") {
                    throw new InconsistentError.BAD_SET ("missing seal wording");
                }
                if (family_fence.contains (asm.crate.family)) {
                    if (family_fence[asm.crate.family] != asm.effective_fence) {
                        throw new InconsistentError.BAD_SET ("conflicting notice");
                    }
                } else {
                    family_fence[asm.crate.family] = asm.effective_fence;
                }

                if (!alpha_by_family.contains (asm.crate.family)) {
                    throw new InconsistentError.BAD_SET ("missing alphabet");
                }
                var alpha = alpha_by_family[asm.crate.family];
                asm.checksum_alphabet = alpha.alphabet_id;
                asm.checksum_priority = alpha.checksum_priority;
                for (int j = 0; j < asm.shards.length; j++) {
                    var dig = asm.shards[j].shard_digest;
                    if (dig.length != alpha.digest_width) {
                        throw new InconsistentError.BAD_SET ("digest width");
                    }
                    for (int p = 0; p < dig.length; p++) {
                        unichar ch = dig.get_char (p);
                        string cs = ch.to_string ();
                        if (alpha.allowed_characters.index_of (cs) < 0) {
                            throw new InconsistentError.BAD_SET ("bad alphabet char");
                        }
                    }
                }

                asm.tier_priority = tier_priority (b, asm.crate.release_tier);
                int d_self = tier_distance (b, asm.crate.release_tier);
                var n = notice_for (b, asm.crate.crate_id);
                if (n.inherited_from == "") {
                    if (d_self != 0) {
                        throw new InconsistentError.BAD_SET ("nonroot without parent");
                    }
                } else {
                    var parent = by_id[n.inherited_from];
                    int d_parent = tier_distance (b, parent.crate.release_tier);
                    if (d_self != d_parent + 1) {
                        throw new InconsistentError.BAD_SET ("tier jump");
                    }
                }

                asm.lane_contrib = asm.byte_total + ancestor_own_sum (asm, by_id, b);
            }

            var candidates = new HashTable<string, GenericArray<LaneRow>> (str_hash, str_equal);
            var lane_cap = new HashTable<string, int> (str_hash, str_equal);
            var lane_used = new HashTable<string, int> (str_hash, str_equal);
            var fill = new HashTable<string, int> (str_hash, str_equal);

            for (int i = 0; i < b.lanes.length; i++) {
                var L = b.lanes[i];
                if (!candidates.contains (L.crate_id)) {
                    candidates[L.crate_id] = new GenericArray<LaneRow> ();
                }
                candidates[L.crate_id].add (L);
                if (lane_cap.contains (L.lane_id)) {
                    if (lane_cap[L.lane_id] != L.capacity_bytes
                        || lane_used[L.lane_id] != L.used_bytes) {
                        throw new InconsistentError.BAD_SET ("lane disagree");
                    }
                } else {
                    lane_cap[L.lane_id] = L.capacity_bytes;
                    lane_used[L.lane_id] = L.used_bytes;
                    fill[L.lane_id] = L.used_bytes;
                }
            }

            var order = new GenericArray<CrateAsm> ();
            for (int i = 0; i < b.assemblies.length; i++) {
                order.add (b.assemblies[i]);
            }
            order.sort_with_data ((a, c) => {
                if (a.notice_priority != c.notice_priority) {
                    return a.notice_priority - c.notice_priority;
                }
                return strcmp (a.crate.crate_id, c.crate.crate_id);
            });

            for (int i = 0; i < order.length; i++) {
                var asm = order[i];
                if (!candidates.contains (asm.crate.crate_id)) {
                    throw new InconsistentError.BAD_SET ("missing lane bid");
                }
                var opts = candidates[asm.crate.crate_id];
                LaneRow? best = null;
                int best_residual = 0;
                for (int j = 0; j < opts.length; j++) {
                    var L = opts[j];
                    int cur_fill = fill[L.lane_id];
                    if (cur_fill + asm.lane_contrib > L.capacity_bytes) {
                        continue;
                    }
                    int residual = L.capacity_bytes - (cur_fill + asm.lane_contrib);
                    if (best == null
                        || L.lane_priority > best.lane_priority
                        || (L.lane_priority == best.lane_priority
                            && residual < best_residual)
                        || (L.lane_priority == best.lane_priority
                            && residual == best_residual
                            && strcmp (L.lane_id, best.lane_id) < 0)) {
                        best = L;
                        best_residual = residual;
                    }
                }
                if (best == null) {
                    throw new InconsistentError.BAD_SET ("lane bid infeasible");
                }
                asm.lane_id = best.lane_id;
                fill[best.lane_id] = fill[best.lane_id] + asm.lane_contrib;
            }
        }
    }
}
