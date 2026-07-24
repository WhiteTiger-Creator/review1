package observables

import (
	"errors"
	"fmt"
	"os"
	"path/filepath"
)

type OutputFile struct {
	Path string
	Data []byte
}

type stagedTarget struct {
	OutputFile
	Temp string
}

func WritePublication(targets []OutputFile) error {
	if len(targets) == 0 {
		return nil
	}
	seen := map[string]bool{}
	staged := make([]stagedTarget, 0, len(targets))
	for _, target := range targets {
		clean := filepath.Clean(target.Path)
		if target.Path == "" || seen[clean] {
			return errors.New("result targets must be non-empty and distinct")
		}
		seen[clean] = true
		if err := os.MkdirAll(filepath.Dir(clean), 0o755); err != nil {
			removeTemps(staged)
			return err
		}
		tmp, err := os.CreateTemp(filepath.Dir(clean), "."+filepath.Base(clean)+".tmp-*")
		if err != nil {
			removeTemps(staged)
			return err
		}
		name := tmp.Name()
		if err := tmp.Chmod(0o644); err == nil {
			_, err = tmp.Write(target.Data)
		}
		if err == nil {
			err = tmp.Sync()
		}
		closeErr := tmp.Close()
		if err == nil {
			err = closeErr
		}
		if err != nil {
			_ = os.Remove(name)
			removeTemps(staged)
			return err
		}
		staged = append(staged, stagedTarget{OutputFile: OutputFile{Path: clean, Data: target.Data}, Temp: name})
	}
	for i := range staged {
		if err := os.Rename(staged[i].Temp, staged[i].Path); err != nil {
			removeTemps(staged[i:])
			return fmt.Errorf("replace %s: %w", staged[i].Path, err)
		}
		staged[i].Temp = ""
	}
	return nil
}

func removeTemps(staged []stagedTarget) {
	for _, item := range staged {
		if item.Temp != "" {
			_ = os.Remove(item.Temp)
		}
	}
}
