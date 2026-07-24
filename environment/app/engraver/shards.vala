namespace Kiln {
    public class Shards {
        // Starter: groups shards and sums bytes.
        public static void assemble_rough (Bundle b) throws Error {
            var by_crate = new HashTable<string, GenericArray<ShardRow>> (str_hash, str_equal);
            for (int i = 0; i < b.shards.length; i++) {
                var s = b.shards[i];
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
                int bytes = 0;
                for (int j = 0; j < list.length; j++) {
                    bytes += list[j].byte_count;
                }
                var asm = new CrateAsm ();
                asm.crate = c;
                asm.shards = list;
                asm.shard_count = list.length;
                asm.byte_total = bytes;
                asm.index_note = c.compression_stamp;
                b.assemblies.add (asm);
            }
        }
    }
}
