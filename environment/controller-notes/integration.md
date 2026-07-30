# Controller integration

The merge kept each desk's evaluation in its own package and added a thin
wiring layer so the controller can call them in a fixed sequence. The wiring
layer holds no evaluation logic of its own; every counter published in a hall
row is produced by the package that owns that stage.
