package glideclash.api;

import glideclash.internal.BlueprintCheck;
import glideclash.internal.EngineState;
import glideclash.internal.ImmutableViews;
import glideclash.internal.InputLedger;
import glideclash.internal.Resimulator;
import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

public final class Engine {
    private final EngineState state;

    private Engine(EngineState state) {
        this.state = state;
    }

    public static Engine start(Blueprint blueprint) {
        Objects.requireNonNull(blueprint, "blueprint");
        BlueprintCheck.validate(blueprint);
        return new Engine(EngineState.create(blueprint));
    }

    public long headTick() {
        return state.headTick;
    }

    public Snapshot snapshot() {
        return ImmutableViews.snapshot(state);
    }

    public InputReceipt submit(InputFrame input) {
        Objects.requireNonNull(input, "input");
        return InputLedger.submit(state, input);
    }

    public List<GlideFrame> advanceTo(long targetTick) {
        if (targetTick < state.headTick) {
            throw new IllegalArgumentException("targetTick");
        }
        if (targetTick == state.headTick) {
            return List.of();
        }
        EngineState backup = state.deepCopy();
        try {
            List<GlideFrame> frames = new ArrayList<>();
            while (state.headTick < targetTick) {
                frames.add(Resimulator.simulateOneTick(state, false));
            }
            return Collections.unmodifiableList(frames);
        } catch (PhysicsException ex) {
            state.restoreFrom(backup);
            throw ex;
        } catch (ArithmeticException ex) {
            long tick = backup.headTick;
            state.restoreFrom(backup);
            throw new PhysicsException("arithmetic", tick, 0);
        }
    }

    public Engine fork() {
        return new Engine(state.deepCopy());
    }
}
