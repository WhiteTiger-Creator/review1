# Security Notes: enrollward-go-scep-issuance-audit

Inspired by smallstep step-ca (github.com/smallstep/certificates) CVE-2026-30836 /
GHSA-q4r8-xm5f-56gw. The codebase under /app/environment is an original implementation
that reproduces the SCEP unauthenticated-issuance vulnerability class; it is not a copy
of the upstream step-ca code, which is Apache licensed.

- Message type authorization (CWE-287), in internal/scep/api.go. The enrollment gate ran
  the challenge check only for PKCSReq and RenewalReq and had no else branch, so an
  UpdateReq (message type 18) reached the signer with no authentication and was issued a
  certificate. The fix rejects any message type that is not an authorized enrollment type
  before signing.

- Unknown message type fall-through (CWE-287), in internal/scep/authority.go. The envelope
  dispatch ended with a bare success return, so an unknown or reserved message type was
  treated as validly decrypted and flowed downstream into a nil dereference. The fix adds a
  default branch that refuses any unknown message type.

- Fail-open challenge (CWE-287), in internal/scep/challenge.go. A provisioner with no
  challenge configured authorized every request, and the comparison was not constant time.
  The fix fails closed when no challenge is configured and compares the presented challenge
  with subtle.ConstantTimeCompare.

- Renewal signer verification (CWE-295), in internal/scep/renewal.go. A renewal was signed
  without checking that the presented signer certificate was issued by this authority or was
  still valid. The fix verifies the signer issuer matches this CA and that the certificate
  has not expired.

- Requested validity clamp (CWE-295), in internal/scep/signer.go. The requested certificate
  validity was honored without an upper bound, so a single enrollment could mint a
  decades-long certificate. The fix clamps the issued validity to the provisioner maximum.

- DNS name-space constraints (CWE-295), in internal/scep/nameconstraints.go. Each provisioner
  declares permitted and excluded DNS subtrees, but the wildcard-SAN check stripped the leading
  "*." and tested only the parent domain against the excluded subtrees. A wildcard such as
  *.corp.example was therefore issued even though it certifies the excluded host
  internal.corp.example one label below. The fix refuses a wildcard SAN whenever any single-label
  host it would certify lands inside an excluded subtree, while still issuing wildcards whose
  whole host set stays within the permitted name space and clear of every excluded subtree. These
  are name constraints enforced on whole DNS labels, so a sibling such as notinternal.corp.example
  is not mistaken for the excluded subtree and a plain SAN outside the permitted space is refused.
