namespace Kiln {
    public class Mirrors {
        // Starter: first mirror with matching input_name, ignoring trust/disagreement.
        public static void choose_rough (Bundle b) throws Error {
            for (int i = 0; i < b.assemblies.length; i++) {
                var asm = b.assemblies[i];
                string mid = "NONE";
                if (asm.shards.length > 0) {
                    string input = asm.shards[0].input_name;
                    for (int k = 0; k < b.mirrors.length; k++) {
                        if (b.mirrors[k].input_name == input) {
                            mid = b.mirrors[k].mirror_id;
                            break;
                        }
                    }
                }
                asm.mirror_id = mid;
            }
        }
    }
}
