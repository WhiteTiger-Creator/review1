package scep

import (
	"fmt"
	"strings"
)

func (a *Authority) Info() string {
	var b strings.Builder
	fmt.Fprintf(&b, "ca.subject=%q\n", a.ca.SubjectCommonName)
	for _, name := range a.registry.order {
		p := a.registry.provisioners[name]
		configured := "false"
		if p.Challenge != "" {
			configured = "true"
		}
		fmt.Fprintf(&b, "provisioner.%s.max_validity_days=%d\n", p.Name, p.MaxValidityDays)
		fmt.Fprintf(&b, "provisioner.%s.challenge_configured=%s\n", p.Name, configured)
		fmt.Fprintf(&b, "provisioner.%s.allow_renewal=%t\n", p.Name, p.AllowRenewal)
		fmt.Fprintf(&b, "provisioner.%s.permitted_dns=%s\n", p.Name, strings.Join(p.PermittedDNS, ","))
		fmt.Fprintf(&b, "provisioner.%s.excluded_dns=%s\n", p.Name, strings.Join(p.ExcludedDNS, ","))
	}
	return b.String()
}
