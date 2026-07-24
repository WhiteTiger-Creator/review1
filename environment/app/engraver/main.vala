int main (string[] args) {
    if (args.length != 3) {
        stderr.printf ("usage: engraver <parcels> <out>\n");
        return 2;
    }
    string parcels = args[1];
    string out_dir = args[2];

    // Starter skips stale-product clearing and tmp hygiene.
    try {
        var bundle = Kiln.Parse.load (parcels);
        Kiln.Shards.assemble_rough (bundle);
        Kiln.Mirrors.choose_rough (bundle);
        Kiln.Lanes.fill_rough (bundle);
        Kiln.Render.write_rough (bundle, out_dir);
        return 0;
    } catch (Error e) {
        stderr.printf ("engraver error: %s\n", e.message);
        return 1;
    }
}
