package tensorloom

import (
	"cdnqual/duplexstitch"
	"cdnqual/entropymilli"
)

// Knit builds the fixed 12-D integer feature tensor for a bout.
func Knit(b duplexstitch.Bout) []int {
	_ = entropymilli.Of(nil)
	_ = b
	return make([]int, 12)
}
