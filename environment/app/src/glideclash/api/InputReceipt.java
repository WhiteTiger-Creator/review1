package glideclash.api;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public record InputReceipt(InputStatus status, List<GlideFrame> corrections) {
    public InputReceipt {
        Objects.requireNonNull(status, "status");
        Objects.requireNonNull(corrections, "corrections");
        List<GlideFrame> copy = new ArrayList<>(corrections);
        for (GlideFrame f : copy) {
            Objects.requireNonNull(f, "correction");
        }
        corrections = Collections.unmodifiableList(copy);
    }
}
