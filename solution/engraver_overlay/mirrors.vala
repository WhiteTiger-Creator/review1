namespace Kiln {
    public class Mirrors {
        static bool mirror_covers_shard (Bundle b, string mirror_id, ShardRow s) {
            for (int k = 0; k < b.mirrors.length; k++) {
                var m = b.mirrors[k];
                if (m.mirror_id == mirror_id
                    && m.input_name == s.input_name
                    && m.mirror_trust == "yes"
                    && m.receipt_digest == s.shard_digest) {
                    return true;
                }
            }
            return false;
        }

        static bool mirror_has_crate_affinity (Bundle b, CrateAsm asm, string mirror_id) {
            for (int j = 0; j < asm.shards.length; j++) {
                if (!mirror_covers_shard (b, mirror_id, asm.shards[j])) {
                    return false;
                }
            }
            return true;
        }

        public static void validate_and_choose (Bundle b) throws Error {
            var trusted_digest = new HashTable<string, string> (str_hash, str_equal);
            for (int i = 0; i < b.mirrors.length; i++) {
                var m = b.mirrors[i];
                if (m.mirror_trust != "yes") {
                    continue;
                }
                if (trusted_digest.contains (m.input_name)) {
                    if (trusted_digest[m.input_name] != m.receipt_digest) {
                        throw new InconsistentError.BAD_SET ("disagreeing mirrors");
                    }
                } else {
                    trusted_digest[m.input_name] = m.receipt_digest;
                }
            }

            for (int i = 0; i < b.assemblies.length; i++) {
                var asm = b.assemblies[i];
                if (asm.shards.length == 0) {
                    throw new InconsistentError.BAD_SET ("no shards");
                }

                for (int j = 0; j < asm.shards.length; j++) {
                    var s = asm.shards[j];
                    bool matched = false;
                    for (int k = 0; k < b.mirrors.length; k++) {
                        var m = b.mirrors[k];
                        if (m.input_name == s.input_name
                            && m.mirror_trust == "yes"
                            && m.receipt_digest == s.shard_digest) {
                            matched = true;
                            break;
                        }
                    }
                    if (!matched) {
                        throw new InconsistentError.BAD_SET ("no trusted mirror");
                    }
                }

                ShardRow? dominant = null;
                for (int j = 0; j < asm.shards.length; j++) {
                    var s = asm.shards[j];
                    if (dominant == null
                        || s.byte_count > dominant.byte_count
                        || (s.byte_count == dominant.byte_count
                            && s.shard_order < dominant.shard_order)) {
                        dominant = s;
                    }
                }

                MirrorRow? best = null;
                bool best_affinity = false;
                for (int k = 0; k < b.mirrors.length; k++) {
                    var m = b.mirrors[k];
                    if (m.input_name != dominant.input_name) {
                        continue;
                    }
                    if (m.mirror_trust != "yes") {
                        continue;
                    }
                    if (m.receipt_digest != dominant.shard_digest) {
                        continue;
                    }
                    bool affinity = mirror_has_crate_affinity (b, asm, m.mirror_id);
                    if (best == null
                        || m.mirror_priority < best.mirror_priority
                        || (m.mirror_priority == best.mirror_priority
                            && affinity && !best_affinity)
                        || (m.mirror_priority == best.mirror_priority
                            && affinity == best_affinity
                            && strcmp (m.mirror_id, best.mirror_id) < 0)) {
                        best = m;
                        best_affinity = affinity;
                    }
                }
                if (best == null) {
                    throw new InconsistentError.BAD_SET ("no dominant mirror");
                }
                asm.mirror_id = best.mirror_id;
            }
        }
    }
}
