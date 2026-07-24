namespace Kiln {
    public errordomain InconsistentError {
        BAD_SET
    }

    public void clear_products (string out_dir) {
        FileUtils.unlink (Path.build_filename (out_dir, "crate.index"));
        FileUtils.unlink (Path.build_filename (out_dir, "seal.manifest"));
    }

    public void clear_tmp () {
        string tmp = "/app/engraving_tmp";
        try {
            var dir = Dir.open (tmp);
            string? name = null;
            while ((name = dir.read_name ()) != null) {
                if (name == ".keep") {
                    continue;
                }
                string path = Path.build_filename (tmp, name);
                if (FileUtils.test (path, FileTest.IS_DIR)) {
                    try {
                        var sub = Dir.open (path);
                        string? n2 = null;
                        while ((n2 = sub.read_name ()) != null) {
                            FileUtils.unlink (Path.build_filename (path, n2));
                        }
                    } catch (Error e2) {
                    }
                    DirUtils.remove (path);
                } else {
                    FileUtils.unlink (path);
                }
            }
        } catch (Error e) {
        }
    }

    public void fail_clean (string out_dir) {
        clear_products (out_dir);
        clear_tmp ();
        Process.exit (1);
    }

    public class StampRow {
        public string stamp = "";
        public int stamp_priority = 0;
    }

    public class CrateRow {
        public string crate_id = "";
        public string family = "";
        public string compression_stamp = "";
        public string release_tier = "";
        public int crate_priority = 0;
        public string seal_token = "";
    }

    public class ShardRow {
        public string shard_id = "";
        public string crate_id = "";
        public int shard_order = 0;
        public string input_name = "";
        public int byte_count = 0;
        public string shard_digest = "";
    }

    public class MirrorRow {
        public string input_name = "";
        public string mirror_id = "";
        public string receipt_digest = "";
        public string mirror_trust = "";
        public int mirror_priority = 0;
    }

    public class NoticeRow {
        public string crate_id = "";
        public string notice_fence = "";
        public string inherited_from = "";
        public int notice_priority = 0;
        public string public_text = "";
    }

    public class LaneRow {
        public string lane_id = "";
        public string crate_id = "";
        public int capacity_bytes = 0;
        public int used_bytes = 0;
        public int lane_priority = 0;
        public string lane_note = "";
    }

    public class ChecksumRow {
        public string alphabet_id = "";
        public string allowed_characters = "";
        public int digest_width = 0;
        public int checksum_priority = 0;
    }

    public class TierRow {
        public string release_tier = "";
        public string predecessor_tier = "";
        public int tier_priority = 0;
        public string tier_wording = "";
    }

    public class CrateAsm {
        public CrateRow crate;
        public GenericArray<ShardRow> shards = new GenericArray<ShardRow> ();
        public int shard_count = 0;
        public int byte_total = 0;
        public string lane_id = "";
        public string mirror_id = "";
        public string effective_fence = "";
        public string effective_public = "";
        public string local_public = "";
        public string root_seal_token = "";
        public int lane_contrib = 0;
        public bool notice_resolved = false;
        public int notice_priority = 0;
        public int tier_priority = 0;
        public int checksum_priority = 0;
        public string index_note = "";
        public string checksum_alphabet = "";
    }

    public class Bundle {
        public GenericArray<StampRow> stamps = new GenericArray<StampRow> ();
        public GenericArray<CrateRow> crates = new GenericArray<CrateRow> ();
        public GenericArray<ShardRow> shards = new GenericArray<ShardRow> ();
        public GenericArray<MirrorRow> mirrors = new GenericArray<MirrorRow> ();
        public GenericArray<NoticeRow> notices = new GenericArray<NoticeRow> ();
        public GenericArray<LaneRow> lanes = new GenericArray<LaneRow> ();
        public GenericArray<ChecksumRow> checksums = new GenericArray<ChecksumRow> ();
        public GenericArray<TierRow> tiers = new GenericArray<TierRow> ();
        public HashTable<string, int> widths = new HashTable<string, int> (str_hash, str_equal);
        public GenericArray<CrateAsm> assemblies = new GenericArray<CrateAsm> ();
        public bool vala_exit = false;
    }

    public class Parse {
        static string trim_field (string s) {
            return s.strip ();
        }

        static GenericArray<string> read_lines (string dir, string name) throws Error {
            string path = Path.build_filename (dir, name);
            string contents;
            FileUtils.get_contents (path, out contents);
            var rows = new GenericArray<string> ();
            foreach (string raw in contents.split ("\n")) {
                string line = raw;
                if (line.length > 0 && line.get_char (line.length - 1) == '\r') {
                    line = line.substring (0, line.length - 1);
                }
                if (line.strip ().length == 0) {
                    continue;
                }
                rows.add (line);
            }
            if (rows.length < 1) {
                throw new InconsistentError.BAD_SET ("empty " + name);
            }
            return rows;
        }

        static int parse_int (string s, string label) throws Error {
            int v;
            if (!int.try_parse (s, out v)) {
                throw new InconsistentError.BAD_SET ("bad int " + label);
            }
            return v;
        }

        public static Bundle load (string dir) throws Error {
            var b = new Bundle ();

            var stamp_lines = read_lines (dir, "stamps.tsv");
            for (int i = 1; i < stamp_lines.length; i++) {
                string[] c = stamp_lines[i].split ("\t");
                if (c.length < 2) {
                    throw new InconsistentError.BAD_SET ("stamp cols");
                }
                var row = new StampRow ();
                row.stamp = trim_field (c[0]);
                row.stamp_priority = parse_int (trim_field (c[1]), "stamp_priority");
                b.stamps.add (row);
            }

            var crate_lines = read_lines (dir, "crates.tsv");
            for (int i = 1; i < crate_lines.length; i++) {
                string[] c = crate_lines[i].split ("\t");
                if (c.length < 6) {
                    throw new InconsistentError.BAD_SET ("crate cols");
                }
                var row = new CrateRow ();
                row.crate_id = trim_field (c[0]);
                row.family = trim_field (c[1]);
                row.compression_stamp = trim_field (c[2]);
                row.release_tier = trim_field (c[3]);
                row.crate_priority = parse_int (trim_field (c[4]), "crate_priority");
                row.seal_token = trim_field (c[5]);
                if (row.compression_stamp == "vala_exit") {
                    b.vala_exit = true;
                }
                b.crates.add (row);
            }

            var shard_lines = read_lines (dir, "shards.tsv");
            for (int i = 1; i < shard_lines.length; i++) {
                string[] c = shard_lines[i].split ("\t");
                if (c.length < 6) {
                    throw new InconsistentError.BAD_SET ("shard cols");
                }
                var row = new ShardRow ();
                row.shard_id = trim_field (c[0]);
                row.crate_id = trim_field (c[1]);
                row.shard_order = parse_int (trim_field (c[2]), "shard_order");
                row.input_name = trim_field (c[3]);
                row.byte_count = parse_int (trim_field (c[4]), "byte_count");
                row.shard_digest = trim_field (c[5]);
                b.shards.add (row);
            }

            var mirror_lines = read_lines (dir, "mirrors.tsv");
            for (int i = 1; i < mirror_lines.length; i++) {
                string[] c = mirror_lines[i].split ("\t");
                if (c.length < 5) {
                    throw new InconsistentError.BAD_SET ("mirror cols");
                }
                var row = new MirrorRow ();
                row.input_name = trim_field (c[0]);
                row.mirror_id = trim_field (c[1]);
                row.receipt_digest = trim_field (c[2]);
                row.mirror_trust = trim_field (c[3]);
                row.mirror_priority = parse_int (trim_field (c[4]), "mirror_priority");
                b.mirrors.add (row);
            }

            var notice_lines = read_lines (dir, "notices.tsv");
            for (int i = 1; i < notice_lines.length; i++) {
                string[] c = notice_lines[i].split ("\t");
                if (c.length < 5) {
                    throw new InconsistentError.BAD_SET ("notice cols");
                }
                var row = new NoticeRow ();
                row.crate_id = trim_field (c[0]);
                row.notice_fence = trim_field (c[1]);
                row.inherited_from = trim_field (c[2]);
                row.notice_priority = parse_int (trim_field (c[3]), "notice_priority");
                row.public_text = (c.length > 4) ? trim_field (c[4]) : "";
                b.notices.add (row);
            }

            var lane_lines = read_lines (dir, "lanes.tsv");
            for (int i = 1; i < lane_lines.length; i++) {
                string[] c = lane_lines[i].split ("\t");
                if (c.length < 6) {
                    throw new InconsistentError.BAD_SET ("lane cols");
                }
                var row = new LaneRow ();
                row.lane_id = trim_field (c[0]);
                row.crate_id = trim_field (c[1]);
                row.capacity_bytes = parse_int (trim_field (c[2]), "capacity");
                row.used_bytes = parse_int (trim_field (c[3]), "used");
                row.lane_priority = parse_int (trim_field (c[4]), "lane_priority");
                row.lane_note = trim_field (c[5]);
                b.lanes.add (row);
            }

            var checksum_lines = read_lines (dir, "checksums.tsv");
            for (int i = 1; i < checksum_lines.length; i++) {
                string[] c = checksum_lines[i].split ("\t");
                if (c.length < 4) {
                    throw new InconsistentError.BAD_SET ("checksum cols");
                }
                var row = new ChecksumRow ();
                row.alphabet_id = trim_field (c[0]);
                row.allowed_characters = trim_field (c[1]);
                row.digest_width = parse_int (trim_field (c[2]), "digest_width");
                row.checksum_priority = parse_int (trim_field (c[3]), "checksum_priority");
                b.checksums.add (row);
            }

            var tier_lines = read_lines (dir, "tiers.tsv");
            for (int i = 1; i < tier_lines.length; i++) {
                string[] c = tier_lines[i].split ("\t");
                if (c.length < 4) {
                    throw new InconsistentError.BAD_SET ("tier cols");
                }
                var row = new TierRow ();
                row.release_tier = trim_field (c[0]);
                row.predecessor_tier = trim_field (c[1]);
                row.tier_priority = parse_int (trim_field (c[2]), "tier_priority");
                row.tier_wording = trim_field (c[3]);
                b.tiers.add (row);
            }

            var width_lines = read_lines (dir, "widths.tsv");
            for (int i = 1; i < width_lines.length; i++) {
                string[] c = width_lines[i].split ("\t");
                if (c.length < 3) {
                    throw new InconsistentError.BAD_SET ("width cols");
                }
                string key = trim_field (c[0]) + "|" + trim_field (c[1]);
                int w = parse_int (trim_field (c[2]), "width");
                if (w <= 0) {
                    throw new InconsistentError.BAD_SET ("nonpositive width");
                }
                b.widths[key] = w;
            }

            return b;
        }
    }
}
