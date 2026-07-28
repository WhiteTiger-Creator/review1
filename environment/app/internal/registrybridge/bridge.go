package registrybridge

import (
	"bytes"
	"context"
	"encoding/json"
	"fmt"
	"os/exec"
)

func Export(ctx context.Context, path string, destination any) error {
	command := exec.CommandContext(ctx, "/usr/local/bin/orbit-registry", "export", "--db", path)
	var stdout, stderr bytes.Buffer
	command.Stdout, command.Stderr = &stdout, &stderr
	if err := command.Run(); err != nil {
		return fmt.Errorf("registry export: %w: %s", err, stderr.String())
	}
	decoder := json.NewDecoder(&stdout)
	decoder.DisallowUnknownFields()
	if err := decoder.Decode(destination); err != nil {
		return fmt.Errorf("decode catalog: %w", err)
	}
	return nil
}
