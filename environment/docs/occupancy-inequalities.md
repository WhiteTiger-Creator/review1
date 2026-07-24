# Capacity Occupancy Physics

Track occupancy is a two-constraint physical model used by the discrete dynamics simulation. After every PUSH or PULL that updates track t:

    n_cars(t) <= max_cars(t)
    sum_{c on t} length_units(c) <= max_length_units(t)

Before each push, the occupancy model rejects any move that would violate either inequality. The sequence solver must choose an alternate classification track or an intermediate LEAD hop so both invariants remain true.

When replaying the move list for validation, every intermediate occupancy state on every track must satisfy both physical limits.
