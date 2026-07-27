package digest

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"

	"wakeclock/internal/model"
)

func State(state model.State) (string, error) {
	data, err := json.Marshal(state)
	if err != nil {
		return "", err
	}
	sum := sha256.Sum256(data)
	return hex.EncodeToString(sum[:]), nil
}
