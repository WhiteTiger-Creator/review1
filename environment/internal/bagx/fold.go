package bagx

import "nubx/drvx/internal/canon"

var deny = map[string]struct{}{
	"__proto__": {}, "constructor": {}, "prototype": {},
}

func clone(v any) any {
	switch t := v.(type) {
	case map[string]any:
		out := make(map[string]any, len(t))
		for k, x := range t {
			out[k] = clone(x)
		}
		return out
	case []any:
		out := make([]any, len(t))
		for i := range t {
			out[i] = clone(t[i])
		}
		return out
	default:
		return t
	}
}

func maskAllowed(m uint32, actors []int) bool {
	allowed := map[int]struct{}{}
	for _, a := range actors {
		allowed[a] = struct{}{}
	}
	for bit := 0; bit < 32; bit++ {
		if m&(1<<bit) != 0 {
			if _, ok := allowed[bit]; !ok {
				return false
			}
		}
	}
	return true
}

func Fold(root, patch any, actors []int) map[string]any {
	var out map[string]any
	if r, ok := root.(map[string]any); ok {
		out = clone(r).(map[string]any)
	} else {
		out = map[string]any{}
	}
	src, _ := patch.(map[string]any)
	walk(out, src, actors, 0)
	return out
}

func walk(dst, src map[string]any, actors []int, depth int) {
	if src == nil || dst == nil || depth > 48 {
		return
	}
	for k, v := range src {
		if depth == 0 {
			if _, bad := deny[k]; bad {
				continue
			}
		}
		if k == "mask" {
			m := canon.AsU32(v)
			if !maskAllowed(m, actors) {
				continue
			}
			dst[k] = float64(m)
			continue
		}
		if vm, ok := v.(map[string]any); ok {
			base, _ := dst[k].(map[string]any)
			next := map[string]any{}
			if base != nil {
				next = clone(base).(map[string]any)
			}
			walk(next, vm, actors, depth+1)
			dst[k] = next
			continue
		}
		if va, ok := v.([]any); ok {
			dst[k] = clone(va)
			continue
		}
		dst[k] = v
	}
}

func ReverseKeys(v any) any {
	m, ok := v.(map[string]any)
	if !ok {
		return v
	}
	keys := make([]string, 0, len(m))
	for k := range m {
		keys = append(keys, k)
	}
	// reverse lexicographic walk is simulated by building a new map after sorting keys reverse
	sortRev := append([]string(nil), keys...)
	for i, j := 0, len(sortRev)-1; i < j; i, j = i+1, j-1 {
		sortRev[i], sortRev[j] = sortRev[j], sortRev[i]
	}
	// Go map iteration is random; construct nested reverse by key order list
	out := map[string]any{}
	// stable reverse: insert in reverse sorted order
	keysSorted := append([]string(nil), keys...)
	// sort ascending then reverse
	for i := 0; i < len(keysSorted); i++ {
		for j := i + 1; j < len(keysSorted); j++ {
			if keysSorted[j] < keysSorted[i] {
				keysSorted[i], keysSorted[j] = keysSorted[j], keysSorted[i]
			}
		}
	}
	for i, j := 0, len(keysSorted)-1; i < j; i, j = i+1, j-1 {
		keysSorted[i], keysSorted[j] = keysSorted[j], keysSorted[i]
	}
	for _, k := range keysSorted {
		out[k] = ReverseKeys(m[k])
	}
	return out
}

func CountEsc(bag map[string]any, actors []int) int {
	esc := 0
	var walk func(any)
	walk = func(v any) {
		m, ok := v.(map[string]any)
		if !ok {
			return
		}
		for k, x := range m {
			if _, bad := deny[k]; bad {
				esc++
			}
			if k == "mask" {
				if !maskAllowed(canon.AsU32(x), actors) {
					esc++
				}
			}
			walk(x)
		}
	}
	walk(bag)
	return esc
}
