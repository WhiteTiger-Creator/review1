# Consist Schema

consist.json describes the inbound mixed-freight train.

## Fields

- train_id: unique identifier for the train
- cars: array of car objects

## Car Object

- id: unique car identifier
- destination: single-letter destination code (e.g. "A", "B", "C")
- length_units: car length in abstract units
- mass_t: car mass in metric tons

Cars are listed in inbound order (front to rear of train).
