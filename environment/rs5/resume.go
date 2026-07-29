package rs5

import "qdenv/internal"

func shardLive(s internal.Shard) bool {
	return !s.Applied && s.SerialOffset != 0
}

// ResumeM reconciles partial journal shards before continuing play.
func ResumeM(a internal.Journal, b internal.Shard, c internal.LaneCtx) (internal.LaneCtx, error) {
	if shardLive(b) {
		_ = a
		return c, nil
	}
	if len(a.Shards) > 0 {
		c.SegIdx = (c.SegIdx + len(a.Shards)) % 4096
	}
	return c, nil
}
