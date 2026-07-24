#!/usr/bin/env python3
from __future__ import annotations

import os
from pathlib import Path

BASE = Path(os.environ.get("SCEP_ENV_DIR", "/app/environment"))
SCEP = BASE / "internal" / "scep"


def replace_once(path: Path, old: str, new: str) -> None:
    text = path.read_text()
    if old not in text:
        raise SystemExit(f"apply_fix: anchor not found in {path}")
    if text.count(old) != 1:
        raise SystemExit(f"apply_fix: anchor is not unique in {path}")
    path.write_text(text.replace(old, new))


def fix_api() -> None:
    old = (
        "\tif msg.MessageType == PKCSReq || msg.MessageType == RenewalReq {\n"
        "\t\tif err := a.ValidateChallenge(p, csr.ChallengePassword); err != nil {\n"
        "\t\t\treturn nil, err\n"
        "\t\t}\n"
        "\t}\n"
    )
    new = (
        "\tif msg.MessageType == PKCSReq || msg.MessageType == RenewalReq {\n"
        "\t\tif err := a.ValidateChallenge(p, csr.ChallengePassword); err != nil {\n"
        "\t\t\treturn nil, err\n"
        "\t\t}\n"
        "\t} else {\n"
        '\t\treturn nil, errAPI("message type %s is not authorized '
        'for certificate enrollment", msg.MessageType)\n'
        "\t}\n"
    )
    replace_once(SCEP / "api.go", old, new)


def fix_authority() -> None:
    # CertRep is a response message type, not an enrollment request. The starter
    # returns nil for it without building a CSR, so api.go dereferences a nil CSR
    # and panics before the authorization check runs. Refuse it here instead.
    replace_once(
        SCEP / "authority.go",
        "\tcase CertRep:\n\t\treturn nil\n",
        "\tcase CertRep:\n"
        '\t\treturn errAuthority("message type %s is a response type, '
        'not an enrollment request", msg.MessageType)\n',
    )
    old = (
        "\tcase GetCert, GetCRL, CertPoll:\n"
        '\t\treturn errAuthority("operation %s is not implemented", msg.MessageType)\n'
        "\t}\n"
        "\n"
        "\treturn nil\n"
        "}\n"
    )
    new = (
        "\tcase GetCert, GetCRL, CertPoll:\n"
        '\t\treturn errAuthority("operation %s is not implemented", msg.MessageType)\n'
        "\tdefault:\n"
        '\t\treturn errAuthority("unknown message type %s is not '
        'accepted for issuance", msg.MessageType)\n'
        "\t}\n"
        "}\n"
    )
    replace_once(SCEP / "authority.go", old, new)


def fix_challenge() -> None:
    path = SCEP / "challenge.go"
    replace_once(
        path,
        "package scep\n\nfunc (a *Authority) ValidateChallenge",
        'package scep\n\nimport "crypto/subtle"\n\n'
        "func (a *Authority) ValidateChallenge",
    )
    old = (
        '\tif p.Challenge == "" {\n'
        "\t\treturn nil\n"
        "\t}\n"
        "\tif presented == p.Challenge {\n"
        "\t\treturn nil\n"
        "\t}\n"
    )
    new = (
        '\tif p.Challenge == "" {\n'
        '\t\treturn errChallenge("provisioner %q has no challenge '
        'configured; enrollment refused", p.Name)\n'
        "\t}\n"
        "\tif subtle.ConstantTimeCompare([]byte(presented), "
        "[]byte(p.Challenge)) == 1 {\n"
        "\t\treturn nil\n"
        "\t}\n"
    )
    replace_once(path, old, new)


def fix_renewal() -> None:
    replace_once(
        SCEP / "renewal.go",
        "package scep\n\nfunc (a *Authority) verifyRenewalSigner",
        'package scep\n\nimport "crypto/subtle"\n\n'
        "func (a *Authority) verifyRenewalSigner",
    )
    old = (
        "\tif signer == nil {\n"
        '\t\treturn errRenewal("renewal request did not present '
        'a signer certificate")\n'
        "\t}\n"
        "\treturn nil\n"
    )
    new = (
        "\tif signer == nil {\n"
        '\t\treturn errRenewal("renewal request did not present '
        'a signer certificate")\n'
        "\t}\n"
        "\tif signer.IssuerCommonName != a.ca.SubjectCommonName {\n"
        '\t\treturn errRenewal("signer certificate was not issued by this authority")\n'
        "\t}\n"
        "\tif signer.NotAfterDays <= 0 {\n"
        '\t\treturn errRenewal("signer certificate has already expired")\n'
        "\t}\n"
        "\tif signer.SubjectCommonName != subject {\n"
        '\t\treturn errRenewal("signer certificate subject does not '
        'match the renewal subject")\n'
        "\t}\n"
        "\texpected := a.ca.SignerFingerprint(signer)\n"
        "\tif subtle.ConstantTimeCompare([]byte(signer.Signature), "
        "[]byte(expected)) != 1 {\n"
        '\t\treturn errRenewal("signer certificate signature is not '
        'valid for this authority")\n'
        "\t}\n"
        "\treturn nil\n"
    )
    replace_once(SCEP / "renewal.go", old, new)


def fix_signer() -> None:
    old = (
        "\tvalidity := csr.RequestedValidityDays\n"
        "\tif validity <= 0 {\n"
        "\t\tvalidity = p.MaxValidityDays\n"
        "\t}\n"
    )
    new = (
        "\tvalidity := csr.RequestedValidityDays\n"
        "\tif validity <= 0 || validity > p.MaxValidityDays {\n"
        "\t\tvalidity = p.MaxValidityDays\n"
        "\t}\n"
    )
    replace_once(SCEP / "signer.go", old, new)


def fix_nameconstraints() -> None:
    # The starter strips the "*." from a wildcard SAN and tests only the parent
    # domain against the excluded subtrees, so it never notices that the wildcard
    # would certify a host one label below (e.g. "*.corp.example" certifies the
    # excluded "internal.corp.example"). Reject a wildcard when any host it
    # certifies lands in an excluded subtree.
    old = (
        "\tfor _, e := range excluded {\n"
        "\t\tif dnsWithin(host, e) {\n"
        "\t\t\treturn true\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn false\n"
    )
    new = (
        "\tfor _, e := range excluded {\n"
        "\t\tif dnsWithin(host, e) {\n"
        "\t\t\treturn true\n"
        "\t\t}\n"
        "\t\tif isWildcard && dnsParent(e) == normDNS(host) {\n"
        "\t\t\treturn true\n"
        "\t\t}\n"
        "\t}\n"
        "\treturn false\n"
    )
    replace_once(SCEP / "nameconstraints.go", old, new)


def main() -> None:
    fix_api()
    fix_authority()
    fix_challenge()
    fix_renewal()
    fix_signer()
    fix_nameconstraints()
    print("apply_fix: all six fixes applied")


if __name__ == "__main__":
    main()
