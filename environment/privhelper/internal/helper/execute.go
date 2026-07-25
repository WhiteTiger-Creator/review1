package helper

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os"
	"os/exec"

	"privhelper/internal/model"
)

// ExecuteResult carries the effect produced by a helper.
type ExecuteResult struct {
	Effect   string
	Reply    model.HelperReply
	Decision string
}

// Execute invokes a resolved helper and parses its reply.
func Execute(res Resolution, req model.Request, binding model.Binding) (ExecuteResult, error) {
	if res.Path == "" {
		return ExecuteResult{}, fmt.Errorf("refusing to execute missing helper %q", res.Name)
	}

	reqJSON, err := json.Marshal(req)
	if err != nil {
		return ExecuteResult{}, fmt.Errorf("marshal request: %w", err)
	}
	bindJSON, err := json.Marshal(binding)
	if err != nil {
		return ExecuteResult{}, fmt.Errorf("marshal binding: %w", err)
	}

	cmd := exec.Command(res.Entry.Interpreter, res.Path)
	cmd.Env = append(os.Environ(),
		"PRIVHELPER_REQUEST="+string(reqJSON),
		"PRIVHELPER_BINDING="+string(bindJSON),
	)

	var stdout, stderr bytes.Buffer
	cmd.Stdout = &stdout
	cmd.Stderr = &stderr
	if err := cmd.Run(); err != nil {
		return ExecuteResult{}, fmt.Errorf("helper %q execution failed: %w (stderr: %s)", res.Name, err, stderr.String())
	}

	reply, err := parseReply(stdout.Bytes())
	if err != nil {
		return ExecuteResult{}, fmt.Errorf("helper %q malformed reply: %w", res.Name, err)
	}

	if err := validateReply(reply, req, binding, res.Entry); err != nil {
		return ExecuteResult{}, fmt.Errorf("helper %q reply rejected: %w", res.Name, err)
	}

	out := ExecuteResult{Effect: reply.Effect, Reply: reply, Decision: reply.Decision}
	if out.Effect == "" {
		out.Effect = res.Entry.Effect
	}
	return out, nil
}

func parseReply(data []byte) (model.HelperReply, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	var reply model.HelperReply
	if err := dec.Decode(&reply); err != nil {
		return model.HelperReply{}, err
	}
	return reply, nil
}

func validateReply(reply model.HelperReply, req model.Request, binding model.Binding, entry model.HelperEntry) error {
	if reply.Status != "ok" {
		return fmt.Errorf("status is %q, want ok", reply.Status)
	}
	if reply.Action != "" && reply.Action != req.Action {
		return fmt.Errorf("action mismatch")
	}
	_ = binding
	_ = entry
	return nil
}
