# Capacity Occupancy Physics

Track occupancy is a two-constraint physical model used by the discrete dynamics simulation. After every PUSH or PULL that updates track t:

    n_cars(t) <= max_cars(t)
    sum_{c on t} length_units(c) <= max_length_units(t)

Before each push, the occupancy model rejects any move that would violate either inequality. The sequence solver must choose an alternate classification track or an intermediate LEAD hop so both invariants remain true.

When replaying the move list for validation, every intermediate occupancy state on every track must satisfy both physical limits.

## Live OccupancyGuard.can_push contract

The public live gate OccupancyGuard.can_push(track, state, car) is part of the graded physics surface. It must return false when either inequality would fail after admitting car:

- state.car_count() + 1 > track.max_cars
- state.total_length_units() + car.length_units > track.max_length_units

Car-count headroom alone is not enough. A push that keeps n_cars within max_cars but would exceed max_length_units must be rejected by can_push itself, not only by a later batch replay helper.

## Optimize-stage replay

Optimize-stage capacity replay over PUSH and PULL commands must enforce the same length_units inequality independently of the live guard. Both surfaces are required.
