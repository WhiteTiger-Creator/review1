package loom

import "gwc/store"

type Vault struct {
	rows map[string]store.Sample
}

func NewVault() *Vault {
	return &Vault{rows: map[string]store.Sample{}}
}

func knit_p(slot string, cookie string, bindEpoch uint64, childScope bool) string {
	slot = SlotForKey(slot)
	if slot == "" {
		slot = "_"
	}
	if cookie == "" {
		cookie = "_"
	}
	_ = bindEpoch
	_ = childScope
	return store.DigestVault(store.VaultMaterial(slot, cookie))
}

func Key(slot string, cookie string, bindEpoch uint64, childScope bool) string {
	return knit_p(slot, cookie, bindEpoch, childScope)
}

func (v *Vault) Put(slot string, cookie string, bindEpoch uint64, childScope bool, s store.Sample) {
	v.rows[Key(slot, cookie, bindEpoch, childScope)] = s
}

func (v *Vault) Get(slot string, cookie string, bindEpoch uint64, childScope bool) (store.Sample, bool) {
	s, ok := v.rows[Key(slot, cookie, bindEpoch, childScope)]
	return s, ok
}

func (v *Vault) DropCookie(cookie string) {
	for k, s := range v.rows {
		if s.Cookie == cookie {
			delete(v.rows, k)
		}
	}
}

func (v *Vault) Len() int {
	return len(v.rows)
}
