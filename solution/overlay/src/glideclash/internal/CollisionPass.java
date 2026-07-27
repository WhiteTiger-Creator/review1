package glideclash.internal;

import glideclash.api.ArenaEvent;
import glideclash.api.PhysicsException;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

public final class CollisionPass {
    private CollisionPass() {}

    public static List<ArenaEvent> resolve(EngineState state, long tick, int subframe) {
        List<ArenaEvent> events = new ArrayList<>();
        Set<String> velocityEmitted = new HashSet<>();

        for (int sweep = 0; sweep < 4; sweep++) {
            List<Contact> contacts = ImpactIsland.orderedContacts(state, state.activePucks());
            Contact chosen = null;
            for (Contact c : contacts) {
                if (stillOverlapping(c) && isApproaching(c)) {
                    chosen = c;
                    break;
                }
            }
            if (chosen == null) {
                // Separate any non-approaching residual overlaps in order
                boolean separated = false;
                for (Contact c : contacts) {
                    if (stillOverlapping(c)) {
                        separate(c);
                        separated = true;
                    }
                }
                if (!separated) {
                    return events;
                }
                // After pure separation, check again
                contacts = ImpactIsland.orderedContacts(state, state.activePucks());
                boolean still = false;
                for (Contact c : contacts) {
                    if (stillOverlapping(c) && isApproaching(c)) {
                        still = true;
                        break;
                    }
                }
                if (!still) {
                    for (Contact c : contacts) {
                        if (stillOverlapping(c)) {
                            separate(c);
                        }
                    }
                    return events;
                }
                continue;
            }

            separate(chosen);
            boolean velChanged = applyVelocity(chosen, state, state.rules.maxSpeed());
            if (velChanged) {
                String key = chosen.primaryId() + "|" + chosen.secondaryId() + "|" + chosen.kind();
                if (velocityEmitted.add(key)) {
                    events.add(new ArenaEvent(
                        tick, subframe, chosen.kind(), chosen.primaryId(), chosen.secondaryId()
                    ));
                    if (chosen.kind() != glideclash.api.EventKind.PUCK) {
                        state.noteRicochet(chosen.primaryId(), tick, subframe);
                    }
                }
            }
        }

        List<Contact> left = ImpactIsland.orderedContacts(state, state.activePucks());
        for (Contact c : left) {
            if (stillOverlapping(c) && isApproaching(c)) {
                throw new PhysicsException("impact-limit", tick, subframe);
            }
        }
        for (Contact c : left) {
            if (stillOverlapping(c)) {
                separate(c);
            }
        }
        return events;
    }

    private static boolean stillOverlapping(Contact c) {
        if (c.target == Contact.Target.PUCK) {
            return Contact.overlaps(c.puckA, c.puckB);
        }
        return Contact.overlaps(c.puckA, c.staticX, c.staticY, c.staticRadius);
    }

    private static boolean isApproaching(Contact c) {
        if (c.target == Contact.Target.PUCK) {
            int aComp = c.xAxis ? c.puckA.vx : c.puckA.vy;
            int bComp = c.xAxis ? c.puckB.vx : c.puckB.vy;
            // lo on negative side when orient < 0; approaching when lo moves toward hi
            return (aComp - bComp) * (c.orient < 0 ? 1 : -1) > 0;
        }
        int puckComp = c.xAxis ? c.puckA.vx : c.puckA.vy;
        int otherComp = 0;
        if (c.target == Contact.Target.PADDLE) {
            otherComp = c.xAxis ? c.paddle.vx : c.paddle.vy;
        }
        int rel = puckComp - otherComp;
        return rel * (c.orient < 0 ? 1 : -1) > 0;
    }

    private static boolean separate(Contact c) {
        if (c.target == Contact.Target.PUCK) {
            return separatePucks(c);
        }
        return separateStatic(c);
    }

    private static boolean separateStatic(Contact c) {
        MutableBody p = c.puckA;
        int need = p.radius + c.staticRadius;
        if (c.xAxis) {
            long dx = (long) p.x - c.staticX;
            int sign;
            if (dx == 0) {
                sign = c.orient < 0 ? -1 : 1;
            } else {
                sign = dx < 0 ? -1 : 1;
            }
            int target = c.staticX + sign * need;
            if (p.x != target) {
                p.x = target;
                return true;
            }
            return false;
        }
        long dy = (long) p.y - c.staticY;
        int sign;
        if (dy == 0) {
            sign = c.orient < 0 ? -1 : 1;
        } else {
            sign = dy < 0 ? -1 : 1;
        }
        int target = c.staticY + sign * need;
        if (p.y != target) {
            p.y = target;
            return true;
        }
        return false;
    }

    private static boolean separatePucks(Contact c) {
        MutableBody lo = c.puckA;
        MutableBody hi = c.puckB;
        int need = lo.radius + hi.radius;
        if (c.xAxis) {
            long cur = Math.abs((long) hi.x - lo.x);
            long gap = need - cur;
            if (gap <= 0) {
                return false;
            }
            int moveNeg = Math.toIntExact((gap + 1) / 2);
            int movePos = Math.toIntExact(gap / 2);
            if (lo.x <= hi.x) {
                lo.x = Math.toIntExact(Math.subtractExact(lo.x, moveNeg));
                hi.x = Math.toIntExact(Math.addExact(hi.x, movePos));
            } else {
                lo.x = Math.toIntExact(Math.addExact(lo.x, moveNeg));
                hi.x = Math.toIntExact(Math.subtractExact(hi.x, movePos));
            }
            return true;
        }
        long cur = Math.abs((long) hi.y - lo.y);
        long gap = need - cur;
        if (gap <= 0) {
            return false;
        }
        int moveNeg = Math.toIntExact((gap + 1) / 2);
        int movePos = Math.toIntExact(gap / 2);
        if (lo.y <= hi.y) {
            lo.y = Math.toIntExact(Math.subtractExact(lo.y, moveNeg));
            hi.y = Math.toIntExact(Math.addExact(hi.y, movePos));
        } else {
            lo.y = Math.toIntExact(Math.addExact(lo.y, moveNeg));
            hi.y = Math.toIntExact(Math.subtractExact(hi.y, movePos));
        }
        return true;
    }

    private static boolean applyVelocity(Contact c, EngineState state, int maxSpeed) {
        if (c.target == Contact.Target.BUMPER) {
            state.bumperResponseOrdinal += 1;
            int effectiveKick = Math.floorDiv(c.kick, state.bumperResponseOrdinal);
            if (c.xAxis) {
                int sign = Integer.compare(c.puckA.x, c.staticX);
                if (sign == 0) {
                    sign = c.orient < 0 ? -1 : 1;
                }
                int v = -c.puckA.vx;
                v = Math.toIntExact(Math.addExact((long) v, (long) sign * effectiveKick));
                c.puckA.vx = Integrator.clampSpeed(v, maxSpeed);
                return true;
            }
            int sign = Integer.compare(c.puckA.y, c.staticY);
            if (sign == 0) {
                sign = c.orient < 0 ? -1 : 1;
            }
            int v = -c.puckA.vy;
            v = Math.toIntExact(Math.addExact((long) v, (long) sign * effectiveKick));
            c.puckA.vy = Integrator.clampSpeed(v, maxSpeed);
            return true;
        }
        if (c.target == Contact.Target.PADDLE) {
            boolean authoritative = Boolean.TRUE.equals(
                state.actionWasAuthoritative.get(c.paddle.player)
            );
            if (c.xAxis) {
                long result;
                if (authoritative) {
                    result = Math.subtractExact(Math.multiplyExact(2L, c.paddle.vx), c.puckA.vx);
                } else {
                    result = Math.subtractExact((long) c.paddle.vx, c.puckA.vx);
                }
                c.puckA.vx = Integrator.clampSpeed(Math.toIntExact(result), maxSpeed);
                return true;
            }
            long result;
            if (authoritative) {
                result = Math.subtractExact(Math.multiplyExact(2L, c.paddle.vy), c.puckA.vy);
            } else {
                result = Math.subtractExact((long) c.paddle.vy, c.puckA.vy);
            }
            c.puckA.vy = Integrator.clampSpeed(Math.toIntExact(result), maxSpeed);
            return true;
        }
        if (c.xAxis) {
            int tmp = c.puckA.vx;
            c.puckA.vx = c.puckB.vx;
            c.puckB.vx = tmp;
        } else {
            int tmp = c.puckA.vy;
            c.puckA.vy = c.puckB.vy;
            c.puckB.vy = tmp;
        }
        return true;
    }
}
