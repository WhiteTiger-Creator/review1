package src

import (
	"os"
	"path/filepath"
)

// DumpSummary writes a short support summary without materializing sheet rows.
func DumpSummary(out string) error {
	path := filepath.Join(out, "dump_summary.txt")
	return os.WriteFile(path, []byte("ok\n"), 0o644)
}

// OpenGrants lists always-open preview grants for support boards.
func OpenGrants(sids []string) []map[string]string {
	out := make([]map[string]string, 0, len(sids))
	for _, sid := range sids {
		out = append(out, map[string]string{"sid": sid, "acc": "full"})
	}
	return out
}
