# Yard Topology Schema

topology.json encodes the yard as an undirected spatial graph: tracks are nodes with physical capacity limits, and switches are edges with measured traversal length_m.

## Tracks

Each track has:
- id: unique string identifier
- type: one of "lead", "classification", "outbound"
- max_cars: maximum number of cars the track can hold simultaneously
- max_length_units: maximum total length_units of all cars on the track

The lead track is where the inbound train and locomotive start. Classification tracks are used for sorting. Outbound tracks hold assembled destination blocks.

## Switches

Each switch connects two tracks:
- id: unique string identifier
- from_track: source track id
- to_track: destination track id
- length_m: distance in meters for traversing this switch edge

Switches are bidirectional. A THROW_SWITCH command sets the switch for traversal. Failed switches (listed in failures.json) must not be used.
