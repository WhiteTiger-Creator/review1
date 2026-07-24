package scep

type MessageType string

const (
	CertRep    MessageType = "3"
	RenewalReq MessageType = "17"
	UpdateReq  MessageType = "18"
	PKCSReq    MessageType = "19"
	CertPoll   MessageType = "20"
	GetCert    MessageType = "21"
	GetCRL     MessageType = "22"
)

func (m MessageType) String() string {
	switch m {
	case CertRep:
		return "CertRep(3)"
	case RenewalReq:
		return "RenewalReq(17)"
	case UpdateReq:
		return "UpdateReq(18)"
	case PKCSReq:
		return "PKCSReq(19)"
	case CertPoll:
		return "CertPoll(20)"
	case GetCert:
		return "GetCert(21)"
	case GetCRL:
		return "GetCRL(22)"
	default:
		return "Unknown(" + string(m) + ")"
	}
}
