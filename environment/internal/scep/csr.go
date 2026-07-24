package scep

func parseCSR(r *Request) (*CSRReqMessage, error) {
	if r.SubjectCommonName == "" {
		return nil, errCSR("certificate request carries no subject common name")
	}
	return &CSRReqMessage{
		SubjectCommonName:     r.SubjectCommonName,
		SANs:                  r.SANs,
		ChallengePassword:     r.Challenge,
		RequestedValidityDays: r.RequestedValidityDays,
	}, nil
}
