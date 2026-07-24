package scep

func (a *Authority) verifyRenewalSigner(signer *SignerCertificate, subject string) error {
	if signer == nil {
		return errRenewal("renewal request did not present a signer certificate")
	}
	return nil
}
