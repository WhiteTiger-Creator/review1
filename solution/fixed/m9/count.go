package m9

import "hxenv/lib/core"

func Count(p core.Plan) int { return len(p.Edges) }
