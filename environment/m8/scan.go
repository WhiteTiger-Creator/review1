package m8

import (
	"os"
)

// ByteScan returns the on-disk size of path in bytes.
func ByteScan(path string) (int64, error) {
	fi, err := os.Stat(path)
	if err != nil {
		return 0, err
	}
	return fi.Size(), nil
}
