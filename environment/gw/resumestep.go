package gw

import (
	"qdenv/internal"
	"qdenv/rs5"
)

func applyResume(journal internal.Journal, st internal.Frame, ctx internal.LaneCtx) (internal.Journal, internal.LaneCtx) {
	shard := internal.Shard{SerialOffset: st.Depth, Applied: false}
	if st.Seq%2 == 0 {
		journal.Shards = append(journal.Shards, shard)
	}
	ctx, _ = rs5.ResumeM(journal, shard, ctx)
	return journal, ctx
}
