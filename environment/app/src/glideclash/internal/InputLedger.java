package glideclash.internal;

import glideclash.api.Action;
import glideclash.api.GlideFrame;
import glideclash.api.InputFrame;
import glideclash.api.InputReceipt;
import glideclash.api.InputStatus;
import java.util.List;
import java.util.Map;
import java.util.TreeMap;

public final class InputLedger {
    private InputLedger() {}

    public static InputReceipt submit(EngineState state, InputFrame input) {
        if (input.tick() < 0 || input.sequence() < 0) {
            return new InputReceipt(InputStatus.INVALID_INPUT, List.of());
        }
        if (!state.players.contains(input.player())) {
            return new InputReceipt(InputStatus.UNKNOWN_PLAYER, List.of());
        }
        EngineState.AuthSlot existing = state.auth(input.player(), input.tick());
        if (existing != null) {
            if (input.sequence() == existing.sequence && input.action() == existing.action) {
                return new InputReceipt(InputStatus.IDEMPOTENT, List.of());
            }
            if (input.sequence() < existing.sequence) {
                return new InputReceipt(InputStatus.STALE_SEQUENCE, List.of());
            }
            if (input.sequence() == existing.sequence) {
                return new InputReceipt(InputStatus.CONFLICT, List.of());
            }
        }
        if (input.tick() < state.headTick) {
            // Starter: no late resimulation
            return new InputReceipt(InputStatus.TOO_OLD, List.of());
        }
        state.putAuth(input.player(), input.tick(), input.sequence(), input.action());
        return new InputReceipt(InputStatus.STORED, List.of());
    }

    public static Map<Integer, Action> chooseActions(EngineState state, long tick) {
        Map<Integer, Action> out = new TreeMap<>();
        for (int player : state.players) {
            out.put(player, Predictor.effective(state, player, tick));
        }
        return out;
    }
}
