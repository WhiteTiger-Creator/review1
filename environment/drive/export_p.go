package drive

import (
	"gwc/loom"
	"gwc/rift"
	"gwc/scroll"
	"gwc/sense"
	"gwc/store"
)

type Export struct {
	Binds  []store.BindingRow
	Traces []store.PrincipalRow
	Probes []store.ProbeRow
	Scopes []store.ScopeRow
}

func RunExport(ctx *store.Ctx, cat *store.Catalog, cycles int) Export {
	alpha := store.SlotRef("alpha-sock")
	childRef := store.SlotRef("beta-child")
	store.CycleWitness = store.RematWitness{}
	scroll.Reset()
	vault := loom.NewVault()
	var facet store.Facet
	var priorCookie string

	var binds []store.BindingRow
	var traces []store.PrincipalRow
	var probes []store.ProbeRow
	var scopes []store.ScopeRow

	for cycle := 0; cycle < cycles; cycle++ {
		if cycle > 0 {
			OpenShift(cat, "vexa")
		}

		ln, err := Listen(ctx, cat)
		if err != nil {
			panic(err)
		}

		path := cat.PathByRef[string(alpha)]
		if path == "" {
			path = ln.Path
		}
		attachEpoch := cat.PolicyGen
		cookie := MintCookie(path, ln.Gen, attachEpoch)
		ln.Cookie = cookie

		if priorCookie != "" && priorCookie != cookie {
			vault.DropCookie(priorCookie)
		}

		steadyMark := "kairo"
		steadyUID := cat.UIDByMark[steadyMark]
		steadySupp := cat.SuppByMark[steadyMark]
		sample := rift.Stamp(string(alpha), path, cookie, steadyUID, steadySupp, steadyMark)
		vault.Put(string(alpha), cookie, attachEpoch, false, sample)
		facet = PublishFacet(facet, sample, string(alpha))
		scroll.Emit("intake", alpha, steadyMark, sample.LaneHex, sample.SuppMask, cat.PolicyGen, cookie)

		binds = append(binds, store.BindingRow{
			Ref:       alpha,
			PolicyGen: attachEpoch,
			PathHex:   store.PathHex(path),
		})
		traces = append(traces, store.PrincipalRow{
			Ref:       alpha,
			MarkHex:   store.MarkHex(sample.UID, sample.Mark),
			SealHex:   sample.LaneHex,
			SuppMask:  sample.SuppMask,
			PolicyGen: cat.PolicyGen,
			Cookie:    cookie,
		})

		live := sample
		if cycle > 0 {
			nextMark := cat.ActiveMark
			nextUID := cat.UIDByMark[nextMark]
			live = HotAdvance(sample, nextUID, nextMark, cat.DropMask, path, cookie, string(alpha))
			vault.Put(string(alpha), cookie, attachEpoch, false, live)
			facet = PublishFacet(facet, live, string(alpha))
			scroll.Emit("rebind", alpha, nextMark, live.LaneHex, live.SuppMask, cat.PolicyGen, cookie)
			traces = append(traces, store.PrincipalRow{
				Ref:       alpha,
				MarkHex:   store.MarkHex(live.UID, live.Mark),
				SealHex:   live.LaneHex,
				SuppMask:  live.SuppMask,
				PolicyGen: cat.PolicyGen,
				Cookie:    cookie,
			})
		}

		childPath := cat.PathByRef[string(childRef)]
		if childPath == "" {
			childPath = path
		}
		childSample := rift.Stamp(string(childRef), childPath, cookie, live.UID, live.SuppMask, live.Mark)
		vault.Put(string(childRef), cookie, attachEpoch, true, childSample)
		childEpoch := ChildEpoch(cat, string(childRef), string(alpha), attachEpoch)
		binds = append(binds, store.BindingRow{
			Ref:       childRef,
			PolicyGen: childEpoch,
			PathHex:   store.PathHex(childPath),
		})
		traces = append(traces, store.PrincipalRow{
			Ref:       childRef,
			MarkHex:   store.MarkHex(childSample.UID, childSample.Mark),
			SealHex:   childSample.LaneHex,
			SuppMask:  childSample.SuppMask,
			PolicyGen: childEpoch,
			Cookie:    cookie,
		})

		selected, ok := vault.Get(string(alpha), cookie, attachEpoch, false)
		pinned, current, sealMatch := MeasurePair(cookie, facet, selected, ok)
		probes = append(probes, store.ProbeRow{
			Ref:       alpha,
			CredSkew:  sense.Skew(sense.Pair{Pinned: int32(pinned), Current: int32(current)}),
			Pinned:    pinned,
			Current:   current,
			SealMatch: sealMatch,
			Cookie:    cookie,
		})

		childSelected, childOk := vault.Get(string(childRef), cookie, attachEpoch, true)
		cpinned, ccurrent, csealMatch := MeasurePair(cookie, facet, childSelected, childOk)
		probes = append(probes, store.ProbeRow{
			Ref:       childRef,
			CredSkew:  sense.Skew(sense.Pair{Pinned: int32(cpinned), Current: int32(ccurrent)}),
			Pinned:    cpinned,
			Current:   ccurrent,
			SealMatch: csealMatch,
			Cookie:    cookie,
		})

		ops := scroll.CountOps()
		cookieAligned := live.Cookie == cookie && childSample.Cookie == cookie
		facetAligned := facet.UID == live.UID && facet.SuppMask == live.SuppMask && facet.Cookie == cookie && facet.SealHex == live.LaneHex
		agree := store.ScoreCycle(live.UID, live.UID, childSample.LaneHex, live.LaneHex, ops, cookieAligned, facetAligned)
		if childSample.LaneKey == string(childRef) && childSample.LaneHex != live.LaneHex {
			agree++
		}
		if cycle > 0 && live.SuppMask&cat.DropMask == 0 {
			agree++
		}
		scopes = append(scopes, store.ScopeRow{
			Cycle:           cycle,
			ScopeAgreeCount: agree,
			TranscriptRows:  len(binds),
			TraceRows:       len(traces),
			JournalRows:     len(scroll.Snapshot()),
		})
		priorCookie = cookie
		FinishCycle(cat)
	}

	return Export{Binds: binds, Traces: traces, Probes: probes, Scopes: scopes}
}
