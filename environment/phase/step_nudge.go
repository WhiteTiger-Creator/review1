package phase

import (
	"environment/k3"
)

func stepNudge(st *k3.Buf, tick k3.Tick, mem k3.Members) int {
	return k3.NudgeA(st, tick, mem)
}
