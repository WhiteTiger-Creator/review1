package helper

import (
	"bytes"
	"encoding/json"
	"fmt"
	"os/exec"

	"privhelper/internal/model"
)

// ExecuteResult carries the validated effect produced by a helper.
type ExecuteResult struct {
	Effect string
	Reply  model.HelperReply
}

// Execute runs the verified helper bytes under the fixed interpreter with a
// minimal, allowlisted environment. The verified content is passed via
// `python3 -c` so the on-disk path is never reopened after verification. The
// reply is then strictly validated against the binding and the manifest effect;
// any deviation is an error and yields no effect.
func Execute(res Resolution, req model.Request, binding model.Binding) (ExecuteResult, error) {
	if !res.Trusted || len(res.Content) == 0 {
		return ExecuteResult{}, fmt.Errorf("refusing to execute untrusted helper %q", res.Name)
	}

	reqJSON, err := json.Marshal(req)
	if err != nil {
		return ExecuteResult{}, fmt.Errorf("marshal request: %w", err)
	}
	bindJSON, err := json.Marshal(binding)
	if err != nil {
		return ExecuteResult{}, fmt.Errorf("marshal binding: %w", err)
	}

	// #nosec G204 -- interpreter is a fixed constant and the program text is the
	// digest-verified helper content, not caller input.
	cmd := exec.Command(res.Entry.Interpreter, "-c", string(res.Content))
	cmd.Env = []string{
		"PATH=/usr/bin:/bin",
		"HOME=/tmp",
		"LANG=C",
		"PRIVHELPER_REQUEST=" + string(reqJSON),
		"PRIVHELPER_BINDING=" + string(bindJSON),
	}

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

	return ExecuteResult{Effect: res.Entry.Effect, Reply: reply}, nil
}

func parseReply(data []byte) (model.HelperReply, error) {
	dec := json.NewDecoder(bytes.NewReader(data))
	// Unknown fields are tolerated but ignored: a helper may include extra keys,
	// none of which can influence authority. Known-but-authority fields such as
	// `decision` are decoded and then discarded by validateReply.
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
	if reply.RequestDigest != binding.RequestDigest {
		return fmt.Errorf("request_digest mismatch")
	}
	if reply.ManifestGeneration != binding.ManifestGeneration {
		return fmt.Errorf("manifest_generation mismatch")
	}
	if reply.ManifestDigest != binding.ManifestDigest {
		return fmt.Errorf("manifest_digest mismatch")
	}
	if reply.Action != req.Action {
		return fmt.Errorf("action mismatch")
	}
	if reply.Unit != req.Unit {
		return fmt.Errorf("unit mismatch")
	}
	if reply.Effect != entry.Effect {
		return fmt.Errorf("effect %q does not match manifest effect %q", reply.Effect, entry.Effect)
	}
	// reply.Decision is deliberately ignored: it can never grant authority.
	return nil
}
