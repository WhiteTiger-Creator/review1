package scep

import "strings"

// normDNS lower-cases a DNS name and drops any trailing root dot so that
// comparisons happen on a single canonical form.
func normDNS(name string) string {
	return strings.ToLower(strings.TrimSuffix(name, "."))
}

// dnsWithin reports whether name sits at or beneath the subtree apex, matching
// only on whole DNS labels (so "notcorp.example" is not within "corp.example").
func dnsWithin(name, subtree string) bool {
	n := normDNS(name)
	s := normDNS(subtree)
	if s == "" {
		return false
	}
	return n == s || strings.HasSuffix(n, "."+s)
}

// dnsParent returns name with its leading label removed, or "" if name is a
// single label.
func dnsParent(name string) string {
	n := normDNS(name)
	if i := strings.IndexByte(n, '.'); i >= 0 {
		return n[i+1:]
	}
	return ""
}

func anyDNSWithin(name string, subtrees []string) bool {
	for _, s := range subtrees {
		if dnsWithin(name, s) {
			return true
		}
	}
	return false
}

// nameHitsExcluded reports whether a SAN meets any excluded subtree.
func nameHitsExcluded(host string, isWildcard bool, excluded []string) bool {
	for _, e := range excluded {
		if dnsWithin(host, e) {
			return true
		}
	}
	return false
}

// authorizeNames rejects a request whose subject-alternative names fall outside
// the provisioner's permitted DNS name space or inside its excluded name space.
// A leading "*." marks a wildcard SAN; host holds the domain beneath it.
func (a *Authority) authorizeNames(p *Provisioner, sans []string) error {
	for _, san := range sans {
		host := san
		isWildcard := false
		if strings.HasPrefix(san, "*.") {
			host = san[2:]
			isWildcard = true
		}
		if len(p.PermittedDNS) > 0 && !anyDNSWithin(host, p.PermittedDNS) {
			return errAuthority(
				"name %q is outside the permitted name space of provisioner %q",
				san, p.Name,
			)
		}
		if nameHitsExcluded(host, isWildcard, p.ExcludedDNS) {
			return errAuthority(
				"name %q meets an excluded name space of provisioner %q",
				san, p.Name,
			)
		}
	}
	return nil
}
