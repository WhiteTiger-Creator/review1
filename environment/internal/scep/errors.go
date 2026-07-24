package scep

import "fmt"

func errAPI(format string, a ...any) error {
	return fmt.Errorf("scep/api: "+format, a...)
}

func errAuthority(format string, a ...any) error {
	return fmt.Errorf("scep/authority: "+format, a...)
}

func errChallenge(format string, a ...any) error {
	return fmt.Errorf("scep/challenge: "+format, a...)
}

func errRenewal(format string, a ...any) error {
	return fmt.Errorf("scep/renewal: "+format, a...)
}

func errSigner(format string, a ...any) error {
	return fmt.Errorf("scep/signer: "+format, a...)
}

func errCSR(format string, a ...any) error {
	return fmt.Errorf("scep/csr: "+format, a...)
}
