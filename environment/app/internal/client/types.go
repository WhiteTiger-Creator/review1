package client

import "orbit.local/sentinel/internal/analysis"

type Fetched struct {
	Tile analysis.Tile
	ETag string
}
