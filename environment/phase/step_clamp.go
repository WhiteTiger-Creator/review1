package phase

import (
	"environment/k3"
	"environment/v2"
)

func stepClamp(st *k3.Buf, lane string, g *v2.Gate) error {
	return v2.ClampC(st, lane, g)
}
