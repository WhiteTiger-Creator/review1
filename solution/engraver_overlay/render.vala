namespace Kiln {
    public class Render {
        static string pad_left (string text, int width) throws Error {
            if (text.length > width) {
                throw new InconsistentError.BAD_SET ("width overflow");
            }
            return text + string.nfill (width - text.length, ' ');
        }

        static string pad_right (string text, int width) throws Error {
            if (text.length > width) {
                throw new InconsistentError.BAD_SET ("width overflow");
            }
            return string.nfill (width - text.length, ' ') + text;
        }

        static int width_of (Bundle b, string product, string column) throws Error {
            string key = product + "|" + column;
            if (!b.widths.contains (key)) {
                throw new InconsistentError.BAD_SET ("missing width");
            }
            return b.widths[key];
        }

        public static void write (Bundle b, string out_dir) throws Error {
            DirUtils.create_with_parents (out_dir, 0755);

            var index_rows = new GenericArray<CrateAsm> ();
            var seal_rows = new GenericArray<CrateAsm> ();
            for (int i = 0; i < b.assemblies.length; i++) {
                index_rows.add (b.assemblies[i]);
                seal_rows.add (b.assemblies[i]);
            }

            // checksum_priority ASC, crate_priority DESC, crate_id ASC
            index_rows.sort_with_data ((a, c) => {
                if (a.checksum_priority != c.checksum_priority) {
                    return a.checksum_priority - c.checksum_priority;
                }
                if (a.crate.crate_priority != c.crate.crate_priority) {
                    return c.crate.crate_priority - a.crate.crate_priority;
                }
                return strcmp (a.crate.crate_id, c.crate.crate_id);
            });

            // effective_fence ASC, notice_priority ASC, crate_id ASC
            seal_rows.sort_with_data ((a, c) => {
                int fcmp = strcmp (a.effective_fence, c.effective_fence);
                if (fcmp != 0) {
                    return fcmp;
                }
                if (a.notice_priority != c.notice_priority) {
                    return a.notice_priority - c.notice_priority;
                }
                return strcmp (a.crate.crate_id, c.crate.crate_id);
            });

            var index = new StringBuilder ();
            index.append ("crate_id family shard_count byte_total lane_id release_tier index_note\n");
            int w_id = width_of (b, "crate.index", "crate_id");
            int w_fam = width_of (b, "crate.index", "family");
            int w_sc = width_of (b, "crate.index", "shard_count");
            int w_bt = width_of (b, "crate.index", "byte_total");
            int w_lane = width_of (b, "crate.index", "lane_id");
            int w_tier = width_of (b, "crate.index", "release_tier");
            int w_note = width_of (b, "crate.index", "index_note");

            for (int i = 0; i < index_rows.length; i++) {
                var a = index_rows[i];
                index.append (pad_left (a.crate.crate_id, w_id));
                index.append (pad_left (a.crate.family, w_fam));
                index.append (pad_right (a.shard_count.to_string (), w_sc));
                index.append (pad_right (a.byte_total.to_string (), w_bt));
                index.append (pad_left (a.lane_id, w_lane));
                index.append (pad_left (a.crate.release_tier, w_tier));
                index.append (pad_left (a.index_note, w_note));
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

            for (int i = 0; i < seal_rows.length; i++) {
                var a = seal_rows[i];
                seal.append (pad_left (a.crate.crate_id, s_id));
                seal.append (pad_left (a.root_seal_token, s_tok));
                seal.append (pad_left (a.mirror_id, s_mir));
                seal.append (pad_left (a.effective_fence, s_fen));
                seal.append (pad_left (a.checksum_alphabet, s_alpha));
                seal.append (pad_left (a.effective_public, s_pub));
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
