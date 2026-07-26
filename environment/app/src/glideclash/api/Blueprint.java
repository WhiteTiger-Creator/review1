package glideclash.api;

import java.util.ArrayList;
import java.util.Collections;
import java.util.Comparator;
import java.util.List;

public record Blueprint(
    Rules rules, List<PuckSeed> pucks, List<PaddleSeed> paddles,
    List<Bumper> bumpers, List<Gate> gates, List<Goal> goals
) {
    public Blueprint {
        pucks = copySort(pucks, Comparator.comparing(PuckSeed::id, Comparator.nullsLast(String::compareTo)));
        paddles = copySort(paddles, Comparator.comparing(PaddleSeed::id, Comparator.nullsLast(String::compareTo)));
        bumpers = copySort(bumpers, Comparator.comparing(Bumper::id, Comparator.nullsLast(String::compareTo)));
        gates = copySort(gates, Comparator.comparing(Gate::id, Comparator.nullsLast(String::compareTo)));
        goals = copySort(goals, Comparator.comparing(Goal::id, Comparator.nullsLast(String::compareTo)));
    }

    private static <T> List<T> copySort(List<T> in, Comparator<T> cmp) {
        if (in == null) {
            return null;
        }
        List<T> copy = new ArrayList<>(in);
        if (copy.contains(null)) {
            return Collections.unmodifiableList(copy);
        }
        copy.sort(cmp);
        return Collections.unmodifiableList(copy);
    }
}
