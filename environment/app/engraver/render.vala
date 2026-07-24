namespace Kiln {
    public class Render {
        // Starter renderer: left-pads fields and writes in assembly order.
        static string pad_field (string text, int width) {
            if (text.length >= width) {
                return text.substring (0, width);
            }
            return text + string.nfill (width - text.length, ' ');
        }

        static int width_of (Bundle b, string product, string column) {
            string key = product + "|" + column;
            if (b.widths.contains (key)) {
                return b.widths[key];
            }
            return 8;
        }

        public static void write_rough (Bundle b, string out_dir) throws Error {
            DirUtils.create_with_parents (out_dir, 0755);

            var index = new StringBuilder ();
            index.append ("crate_id family shard_count byte_total lane_id release_tier index_note\n");
            int w_id = width_of (b, "crate.index", "crate_id");
            int w_fam = width_of (b, "crate.index", "family");
            int w_sc = width_of (b, "crate.index", "shard_count");
            int w_bt = width_of (b, "crate.index", "byte_total");
            int w_lane = width_of (b, "crate.index", "lane_id");
            int w_tier = width_of (b, "crate.index", "release_tier");
            int w_note = width_of (b, "crate.index", "index_note");

            for (int i = 0; i < b.assemblies.length; i++) {
                var a = b.assemblies[i];
                index.append (pad_field (a.crate.crate_id, w_id));
                index.append (pad_field (a.crate.family, w_fam));
                index.append (pad_field (a.shard_count.to_string (), w_sc));
                index.append (pad_field (a.byte_total.to_string (), w_bt));
                index.append (pad_field (a.lane_id, w_lane));
                index.append (pad_field (a.crate.release_tier, w_tier));
                index.append (pad_field (a.index_note, w_note));
                index.append ("\n");
            }

            var seal = new StringBuilder ();
            seal.append ("crate_id seal_token mirror_id notice_fence checksum_alphabet public_seal_text\n");
            int s_id = width_of (b, "seal.manifest", "crate_id");
            int s_tok = width_of (b, "seal.manifest", "seal_token");
            int s_mir = width_of (b, "seal.manifest", "mirror_id");
            int s_fen = width_of (b, "seal.manifest", "notice_fence");
            int s_alpha = width_of (b, "seal.manifest", "checksum_alphabet");
            int s_pub = width_of (b, "seal.manifest", "public_seal_text");

            for (int i = 0; i < b.assemblies.length; i++) {
                var a = b.assemblies[i];
                seal.append (pad_field (a.crate.crate_id, s_id));
                seal.append (pad_field (a.crate.seal_token, s_tok));
                seal.append (pad_field (a.mirror_id, s_mir));
                seal.append (pad_field (a.effective_fence, s_fen));
                seal.append (pad_field (a.checksum_alphabet, s_alpha));
                seal.append (pad_field (a.effective_public, s_pub));
                seal.append ("\n");
            }

            FileUtils.set_contents (
                Path.build_filename (out_dir, "crate.index"),
                index.str
            );
            FileUtils.set_contents (
                Path.build_filename (out_dir, "seal.manifest"),
                seal.str
            );
        }
    }
}
