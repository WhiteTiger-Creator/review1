namespace Kiln {
    public class Shards {
        static bool seal_ok (string token) {
            return token == "KILN_SEAL" || token == "AMBER_SEAL"
                || token == "BRONZE_SEAL" || token == "UMBER_SEAL";
        }

        public static void assemble (Bundle b) throws Error {
            var stamp_set = new HashTable<string, int> (str_hash, str_equal);
            for (int i = 0; i < b.stamps.length; i++) {
                if (stamp_set.contains (b.stamps[i].stamp)) {
                    throw new InconsistentError.BAD_SET ("dup stamp");
                }
                stamp_set[b.stamps[i].stamp] = b.stamps[i].stamp_priority;
            }

            var seen_crate = new HashTable<string, bool> (str_hash, str_equal);
            var crate_by_id = new HashTable<string, CrateRow> (str_hash, str_equal);

            for (int i = 0; i < b.crates.length; i++) {
                var c = b.crates[i];
                if (seen_crate.contains (c.crate_id)) {
                    throw new InconsistentError.BAD_SET ("repeated crate");
                }
                seen_crate[c.crate_id] = true;
                if (c.compression_stamp != "vala_exit" && !stamp_set.contains (c.compression_stamp)) {
                    throw new InconsistentError.BAD_SET ("unknown stamp");
                }
                if (!seal_ok (c.seal_token)) {
                    throw new InconsistentError.BAD_SET ("bad seal token");
                }
                crate_by_id[c.crate_id] = c;
            }

            var seen_shard = new HashTable<string, bool> (str_hash, str_equal);
            var by_crate = new HashTable<string, GenericArray<ShardRow>> (str_hash, str_equal);

            for (int i = 0; i < b.shards.length; i++) {
                var s = b.shards[i];
                if (seen_shard.contains (s.shard_id)) {
                    throw new InconsistentError.BAD_SET ("repeated shard");
                }
                seen_shard[s.shard_id] = true;
                if (!crate_by_id.contains (s.crate_id)) {
                    throw new InconsistentError.BAD_SET ("orphan shard");
                }
                if (!by_crate.contains (s.crate_id)) {
                    by_crate[s.crate_id] = new GenericArray<ShardRow> ();
                }
                by_crate[s.crate_id].add (s);
            }

            for (int i = 0; i < b.crates.length; i++) {
                var c = b.crates[i];
                var list = by_crate[c.crate_id];
                if (list == null) {
                    list = new GenericArray<ShardRow> ();
                }
                list.sort_with_data ((a, b2) => {
                    if (a.shard_order < b2.shard_order) return -1;
                    if (a.shard_order > b2.shard_order) return 1;
                    return strcmp (a.shard_id, b2.shard_id);
                });

                var order_seen = new HashTable<string, bool> (str_hash, str_equal);
                int max_order = 0;
                int bytes = 0;
                for (int j = 0; j < list.length; j++) {
                    var s = list[j];
                    string ok = s.shard_order.to_string ();
                    if (order_seen.contains (ok)) {
                        throw new InconsistentError.BAD_SET ("dup shard order");
                    }
                    order_seen[ok] = true;
                    if (s.shard_order > max_order) {
                        max_order = s.shard_order;
                    }
                    bytes += s.byte_count;
                }
                if (list.length > 0) {
                    if (max_order != list.length) {
                        throw new InconsistentError.BAD_SET ("shard order gap");
                    }
                    for (int k = 1; k <= max_order; k++) {
                        if (!order_seen.contains (k.to_string ())) {
                            throw new InconsistentError.BAD_SET ("shard order skip");
                        }
                    }
                }

                var asm = new CrateAsm ();
                asm.crate = c;
                asm.shards = list;
                asm.shard_count = list.length;
                asm.byte_total = bytes;
                asm.index_note = "";
                b.assemblies.add (asm);
            }
        }
    }
}
