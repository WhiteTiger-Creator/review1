package scep

func (a *Authority) SignCSR(p *Provisioner, csr *CSRReqMessage) (*Certificate, error) {
	if p.MaxValidityDays <= 0 {
		return nil, errSigner("provisioner %q has no issuance validity configured", p.Name)
	}

	validity := csr.RequestedValidityDays
	if validity <= 0 {
		validity = p.MaxValidityDays
	}

	cert := &Certificate{
		Serial:            a.ca.issueSerial(),
		SubjectCommonName: csr.SubjectCommonName,
		IssuerCommonName:  a.ca.SubjectCommonName,
		NotAfterDays:      validity,
		Provisioner:       p.Name,
	}
	return cert, nil
}
