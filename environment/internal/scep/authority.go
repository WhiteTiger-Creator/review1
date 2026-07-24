package scep

type Authority struct {
	ca       *CA
	registry *Registry
}

func NewAuthority() *Authority {
	return &Authority{
		ca:       NewCA(),
		registry: DefaultRegistry(),
	}
}

func (a *Authority) CA() *CA {
	return a.ca
}

func (a *Authority) Registry() *Registry {
	return a.registry
}

func (a *Authority) DecryptPKIEnvelope(msg *PKIMessage) error {
	switch msg.MessageType {
	case CertRep:
		return nil
	case PKCSReq, UpdateReq, RenewalReq:
		csr, err := parseCSR(msg.raw)
		if err != nil {
			return err
		}
		msg.CSRReqMessage = csr
		return nil
	case GetCert, GetCRL, CertPoll:
		return errAuthority("operation %s is not implemented", msg.MessageType)
	}

	return nil
}
