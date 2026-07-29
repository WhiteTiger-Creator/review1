package phase

import (
	"environment/k3"
	"environment/m8"
)

func stepWeave(path string, mem k3.Members) (*m8.WeaveResult, error) {
	return m8.WeaveB(path, mem)
}
