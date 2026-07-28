package hearth

import (
	"fmt"

	"gwc/store"
)

func Normalize(gen uint64) uint64 {
	return store.CycleWitness.MintGen(gen)
}

func FormatGen(gen uint64) string {
	return fmt.Sprintf("gen:%d", gen)
}
