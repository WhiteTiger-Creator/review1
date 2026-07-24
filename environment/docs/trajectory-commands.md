# Sequence Commands

The OccupancyTrajectory produces an array of commands. Each command has a type field.

## Command Types

### THROW_SWITCH
Sets a switch for traversal.
- switch_id: the switch to throw

A THROW_SWITCH command must never reference a switch listed in failures.json.

### PUSH
Locomotive pushes cars from one track to another.
- from_track, to_track: track identifiers
- car_ids: list of car identifiers being pushed

### PULL
Locomotive pulls cars from one track to another.
- from_track, to_track: track identifiers
- car_ids: list of car identifiers being pulled

### MOVE_LOCO
Locomotive moves without cars.
- from_track, to_track: track identifiers

## Distance Accounting

Each PUSH, PULL, or MOVE_LOCO command traverses a switch edge. The distance for the command is edge.length_m of the traversed switch. Total distance is the sum of all command distances. Distance is measured in meters, not hop count.
