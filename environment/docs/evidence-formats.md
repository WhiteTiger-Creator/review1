# Evidence file formats — GW-Basin-12

Field reference for the read-only evidence set. Field names are stable across
the campaign; file names are not meaningful.

## Mesh export (`/app/data/mesh/`)

```
cell_id             string
basin_id            string
area_m2             number, plan area of the finite-volume cell
face_area_m2        number, cross-sectional area of the lateral exchange face
sat_thickness_m     number, saturated thickness used to convert transmissivity
archival_k_m_per_d  number, conductivity recorded by an earlier interpretation
archival_sy         number, specific yield recorded by an earlier interpretation
```

## Aquifer tests (`/app/data/aquifer_tests/`)

```
cell_id                  string
basin_id                 string
discharge_m3_per_d       number, constant pumping rate held during the test
samples[]                array of timed drawdown readings
  elapsed_min                number, minutes since pumping start
  drawdown_m                 number, observed drawdown
  in_straight_line_window    boolean, semi-logarithmic straight-line regime
```

Early readings precede the straight-line regime and are logged with the window
flag clear. They are retained so the recovery of the test can be audited.

## Storage response (`/app/data/storage_response/`)

```
cell_id            string
basin_id           string
records[]          array of injection trials
  injected_volume_m3   number, metered volume delivered to the cell
  head_rise_m          number, head rise observed for that volume
```

## Calibration campaign (`/app/data/calibration/`)

```
campaign_id          string
cell_id              string
basin_id             string
period_days          number
precip_mm            number
pet_mm               number
head_start_m         number
head_end_m           number
hydraulic_gradient   number
pump_m3              number, net metered abstraction over the record
qualified            boolean, record admissibility for coefficient identification
```

Unqualified records are retained for provenance. A record can lose qualification
for metering faults, an incomplete head record, or an unlogged transfer during
the campaign window.

## Reporting stress periods (`/app/data/observations/`)

```
period_id            string
cell_id              string
basin_id             string
period_days          number
precip_mm            number
pet_mm               number
head_start_m         number
head_end_m           number
hydraulic_gradient   number
pump_m3              number, net metered abstraction over the period
```

Negative `pump_m3` denotes a net managed recharge delivery rather than an
abstraction. Negative `hydraulic_gradient` denotes net lateral outflow.
