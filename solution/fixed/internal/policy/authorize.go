// Package policy evaluates authorization decisions strictly from the signed
// manifest. The dispatcher consults this package before any helper runs, and a
// helper reply can never change the outcome.
package policy

import "privhelper/internal/model"

// Result describes an authorization outcome and why it was reached.
type Result struct {
	Authorized bool
	Reason     string
}

// Authorize returns whether the principal may perform the action according to
// the signed manifest policy map. Authority derives exclusively from the
// manifest; no caller input or helper reply is consulted.
func Authorize(m model.Manifest, principal, action string) Result {
	actions, ok := m.Policy[principal]
	if !ok {
		return Result{Authorized: false, Reason: "principal_not_in_policy"}
	}
	for _, a := range actions {
		if a == action {
			return Result{Authorized: true, Reason: "authorized_by_manifest"}
		}
	}
	return Result{Authorized: false, Reason: "action_not_permitted"}
}
