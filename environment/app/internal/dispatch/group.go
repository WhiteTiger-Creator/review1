package dispatch

import (
	"crypto/sha256"
	"encoding/hex"
	"sort"
	"strings"
	"time"

	"wakeclock/internal/model"
)

func IDs(group []model.Occurrence) (string, string, string, []string) {
	ids := make([]string, 0, len(group))
	effective := ""
	for _, item := range group {
		ids = append(ids, item.OccurrenceID)
		if effective == "" || item.DelayedUTC < effective {
			effective = item.DelayedUTC
		}
	}
	sort.Strings(ids)
	groupSum := sha256.Sum256([]byte(strings.Join(ids, "\n")))
	groupID := hex.EncodeToString(groupSum[:])
	activationSum := sha256.Sum256([]byte("activation\n" + groupID + "\n"))
	if parsed, err := time.Parse(time.RFC3339, effective); err == nil {
		effective = parsed.UTC().Format(time.RFC3339)
	}
	return groupID, hex.EncodeToString(activationSum[:]), effective, ids
}
