int main (string[] args) {
    if (args.length != 3) {
        stderr.printf ("usage: engraver <parcels> <out>\n");
        return 2;
    }
    string parcels = args[1];
    string out_dir = args[2];

    Kiln.clear_products (out_dir);
    Kiln.clear_tmp ();

    try {
        DirUtils.create_with_parents ("/app/engraving_tmp", 0755);
        FileUtils.set_contents (
            Path.build_filename ("/app/engraving_tmp", "chip.tmp"),
            "working\n"
        );

        var bundle = Kiln.Parse.load (parcels);
        if (bundle.vala_exit) {
            throw new Kiln.InconsistentError.BAD_SET ("vala_exit");
        }

        Kiln.Shards.assemble (bundle);
        Kiln.Mirrors.validate_and_choose (bundle);
        Kiln.Lanes.resolve_notices_and_lanes (bundle);
        Kiln.Render.write (bundle, out_dir);

        Kiln.clear_tmp ();
        return 0;
    } catch (Error e) {
        Kiln.fail_clean (out_dir);
        return 1;
    }
}
