package scep

type Provisioner struct {
	Name            string
	Challenge       string
	MaxValidityDays int
	AllowRenewal    bool
	// PermittedDNS and ExcludedDNS bound the DNS name space this provisioner may
	// certify, expressed as subtree apexes (RFC 5280 name-constraint style). An
	// empty PermittedDNS imposes no upper bound; ExcludedDNS always carves names
	// back out. A certificate must never be able to certify a name outside the
	// permitted space or inside the excluded space.
	PermittedDNS []string
	ExcludedDNS  []string
}

type Registry struct {
	provisioners map[string]*Provisioner
	order        []string
}

func DefaultRegistry() *Registry {
	return &Registry{
		provisioners: map[string]*Provisioner{
			"default": {
				Name:            "default",
				Challenge:       "s3cr3t-default",
				MaxValidityDays: 90,
				AllowRenewal:    true,
				PermittedDNS:    []string{"corp.example"},
				ExcludedDNS:     []string{"internal.corp.example"},
			},
			"iot":     {Name: "iot", Challenge: "iot-enroll-2026", MaxValidityDays: 30, AllowRenewal: true},
			"open":    {Name: "open", Challenge: "", MaxValidityDays: 90, AllowRenewal: true},
			"legacy":  {Name: "legacy", Challenge: "", MaxValidityDays: 60, AllowRenewal: true},
			"sensor":  {Name: "sensor", Challenge: "", MaxValidityDays: 45, AllowRenewal: true},
			"gateway": {Name: "gateway", Challenge: "", MaxValidityDays: 180, AllowRenewal: true},
		},
		order: []string{"default", "iot", "open", "legacy", "sensor", "gateway"},
	}
}

func (r *Registry) Lookup(name string) (*Provisioner, error) {
	if name == "" {
		name = "default"
	}
	p, ok := r.provisioners[name]
	if !ok {
		return nil, errAPI("unknown provisioner %q", name)
	}
	return p, nil
}
