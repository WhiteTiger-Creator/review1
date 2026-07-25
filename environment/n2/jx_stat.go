package n2

import "os"

func Size(v string) int64 {
	x, _ := os.Stat(Path(v))
	if x == nil {
		return 0
	}
	return x.Size()
}
