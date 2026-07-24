package scep

func (a *Authority) PKIOperation(r *Request) (*Response, error) {
	msg := newPKIMessage(r)

	if err := a.DecryptPKIEnvelope(msg); err != nil {
		return nil, err
	}

	p, err := a.registry.Lookup(msg.Provisioner)
	if err != nil {
		return nil, err
	}

	csr := msg.CSRReqMessage
	if csr.SubjectCommonName == "" {
		return nil, errAPI("certificate request is missing a subject")
	}

	if msg.MessageType == PKCSReq || msg.MessageType == RenewalReq {
		if err := a.ValidateChallenge(p, csr.ChallengePassword); err != nil {
			return nil, err
		}
	}

	if msg.MessageType == RenewalReq {
		if err := a.verifyRenewalSigner(msg.Signer, csr.SubjectCommonName); err != nil {
			return nil, err
		}
	}

	if err := a.authorizeNames(p, csr.SANs); err != nil {
		return nil, err
	}

	cert, err := a.SignCSR(p, csr)
	if err != nil {
		return nil, err
	}

	return &Response{Certificate: cert}, nil
}
