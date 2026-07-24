package scep

func (a *Authority) ValidateChallenge(p *Provisioner, presented string) error {
	if p.Challenge == "" {
		return nil
	}
	if presented == p.Challenge {
		return nil
	}
	return errChallenge("challenge password rejected for provisioner %q", p.Name)
}
