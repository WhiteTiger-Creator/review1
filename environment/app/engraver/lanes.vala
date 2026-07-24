namespace Kiln {
    public class Lanes {
        // Starter: local notice fields and first matching lane row only.
        public static void fill_rough (Bundle b) throws Error {
            for (int i = 0; i < b.assemblies.length; i++) {
                var asm = b.assemblies[i];
                asm.effective_fence = "FENCE_LOCAL";
                asm.effective_public = "local_text";
                asm.notice_priority = 99;
                asm.tier_priority = 99;
                asm.lane_id = "LANE1";
                asm.checksum_alphabet = asm.crate.family;
                for (int j = 0; j < b.notices.length; j++) {
                    if (b.notices[j].crate_id == asm.crate.crate_id) {
                        asm.effective_fence = b.notices[j].notice_fence;
                        asm.effective_public = b.notices[j].public_text;
                        asm.notice_priority = b.notices[j].notice_priority;
                        break;
                    }
                }
                for (int j = 0; j < b.lanes.length; j++) {
                    if (b.lanes[j].crate_id == asm.crate.crate_id) {
                        asm.lane_id = b.lanes[j].lane_id;
                        break;
                    }
                }
                for (int j = 0; j < b.tiers.length; j++) {
                    if (b.tiers[j].release_tier == asm.crate.release_tier) {
                        asm.tier_priority = b.tiers[j].tier_priority;
                        break;
                    }
                }
            }
        }
    }
}
