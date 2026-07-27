package vault

import "cqrun/knot"

func vault_w(led *Ledger, book *knot.Book, epoch int) error {
	if led == nil {
		return errNilLedger
	}
	led.Barrier = epoch
	led.SnapW = map[string]float64{}
	for k, w := range book.W {
		led.SnapW[k] = w
	}
	led.TrustSnap = false
	return led.Persist()
}

func ApplyVault(led *Ledger, book *knot.Book, epoch int) error {
	return vault_w(led, book, epoch)
}

func AppendAdmit(led *Ledger, e Entry) error {
	if led == nil {
		return errNilLedger
	}
	led.Entries = append(led.Entries, e)
	return nil
}

func ResumeInto(led *Ledger, book *knot.Book) error {
	if led == nil || book == nil {
		return errNilLedger
	}
	if err := led.Load(); err != nil {
		return err
	}
	book.ResetFromPriors()
	knot.MarkFrozen(book, false)
	for _, e := range led.Entries {
		if e.Role != "train" {
			continue
		}
		if _, _, err := knot.ApplyKnot(book, e.SID, e.IID, true); err != nil {
			return err
		}
	}
	return nil
}

func TrainForbidden(led *Ledger, epoch, fenceLag int) map[string]bool {
	out := map[string]bool{}
	if led == nil {
		return out
	}
	for _, e := range led.Entries {
		if e.Role != "train" {
			continue
		}
		if epoch-fenceLag <= e.Epoch && e.Epoch <= epoch-1 {
			out[Key(e.SID, e.IID)] = true
		}
	}
	return out
}
