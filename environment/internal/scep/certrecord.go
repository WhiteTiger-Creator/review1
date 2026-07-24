package scep

import "fmt"

type Certificate struct {
	Serial            int64
	SubjectCommonName string
	IssuerCommonName  string
	NotAfterDays      int
	Provisioner       string
}

type Response struct {
	Certificate *Certificate
}

func (r *Response) String() string {
	c := r.Certificate
	return fmt.Sprintf(
		"ISSUED serial=%d cn=%q issuer=%q not_after_days=%d provisioner=%s",
		c.Serial, c.SubjectCommonName, c.IssuerCommonName, c.NotAfterDays, c.Provisioner,
	)
}
