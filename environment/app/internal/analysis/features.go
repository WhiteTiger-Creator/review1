package analysis

import "fmt"

func Extract(tile Tile) (Features, error) {
	_ = tile
	return Features{}, fmt.Errorf("feature extraction is not implemented")
}
