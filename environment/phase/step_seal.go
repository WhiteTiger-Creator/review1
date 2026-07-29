package phase

import (
	"environment/s4"
)

func stepSeal(woven map[string]int, hintPath string, journalGen int) (map[string]int, error) {
	return s4.SealD(woven, hintPath, journalGen)
}
