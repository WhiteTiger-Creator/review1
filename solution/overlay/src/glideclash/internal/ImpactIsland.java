package glideclash.internal;

import glideclash.api.EventKind;
import java.util.ArrayList;
import java.util.Comparator;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Set;

public final class ImpactIsland {
    private ImpactIsland() {}

    public static List<Contact> orderedContacts(
        EngineState state, List<MutableBody> activePucks
    ) {
        // Build puck-puck edges and attach static/paddle contacts
        Map<String, List<String>> edges = new HashMap<>();
        for (MutableBody p : activePucks) {
            edges.put(p.id, new ArrayList<>());
        }
        List<Contact> puckContacts = new ArrayList<>();
        for (int i = 0; i < activePucks.size(); i++) {
            for (int j = i + 1; j < activePucks.size(); j++) {
                MutableBody a = activePucks.get(i);
                MutableBody b = activePucks.get(j);
                if (Contact.overlaps(a, b)) {
                    edges.get(a.id).add(b.id);
                    edges.get(b.id).add(a.id);
                    puckContacts.add(Contact.puck(a, b));
                }
            }
        }
        Map<String, List<Contact>> attached = new HashMap<>();
        for (MutableBody p : activePucks) {
            attached.put(p.id, new ArrayList<>());
            for (var bumper : state.bumpers) {
                if (Contact.overlaps(p, bumper.x(), bumper.y(), bumper.radius())) {
                    attached.get(p.id).add(Contact.bumper(
                        p, bumper.id(), bumper.x(), bumper.y(), bumper.radius(), bumper.kick()
                    ));
                }
            }
            for (MutableBody pad : state.paddles) {
                if (Contact.overlaps(p, pad)) {
                    attached.get(p.id).add(Contact.paddle(p, pad));
                }
            }
        }
        // Connected components by puck-puck edges; isolated pucks with static contacts are components too
        Set<String> seen = new HashSet<>();
        List<List<String>> components = new ArrayList<>();
        for (MutableBody p : activePucks) {
            if (!seen.add(p.id)) {
                continue;
            }
            List<String> comp = new ArrayList<>();
            ArrayList<String> stack = new ArrayList<>();
            stack.add(p.id);
            while (!stack.isEmpty()) {
                String cur = stack.remove(stack.size() - 1);
                comp.add(cur);
                for (String n : edges.get(cur)) {
                    if (seen.add(n)) {
                        stack.add(n);
                    }
                }
            }
            comp.sort(String::compareTo);
            components.add(comp);
        }
        components.sort(Comparator.comparing(c -> c.get(0)));

        List<Contact> ordered = new ArrayList<>();
        for (List<String> comp : components) {
            List<Contact> local = new ArrayList<>();
            Set<String> inComp = new HashSet<>(comp);
            for (String id : comp) {
                local.addAll(attached.get(id));
            }
            for (Contact c : puckContacts) {
                if (inComp.contains(c.puckA.id) && inComp.contains(c.puckB.id)) {
                    local.add(c);
                }
            }
            local.sort(Comparator
                .comparingInt((Contact c) -> kindRank(c.kind()))
                .thenComparing(Contact::primaryId)
                .thenComparing(Contact::secondaryId));
            ordered.addAll(local);
        }
        return ordered;
    }

    private static int kindRank(EventKind k) {
        return switch (k) {
            case BUMPER -> 0;
            case PADDLE -> 1;
            case PUCK -> 2;
            default -> 9;
        };
    }
}
