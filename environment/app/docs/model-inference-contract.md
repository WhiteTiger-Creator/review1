# Model inference contract

The physics-informed coefficient model infers `Cn`, `Ca`, `Cl`, `Cd`, and `Cm` from paired tap features:

- Trapezoidal integration of normal/axial contributions.
- Angle of attack converted from degrees to radians before the Cl/Cd rotation.
- Pitching moment about `xref_c` (facility campaigns use quarter-chord).

Inference must not use left-Riemann sums, degrees-as-radians, leading-edge moments when `xref_c=0.25`, or the decoy Prandtl–Glauert helper.
