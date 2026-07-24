package diagnostic

import (
	"encoding/json"
	"fmt"
	"os"
)

// Failure is one stable scientific diagnostic line on stderr.
type Failure struct {
	Code    string `json:"code"`
	Message string `json:"message"`
}

// Emit writes one JSON diagnostic line to stderr and returns a nonzero status.
func Emit(code, message string) int {
	line, err := json.Marshal(Failure{Code: code, Message: message})
	if err != nil {
		fmt.Fprintf(os.Stderr, "{\"code\":\"E_MAP\",\"message\":\"diagnostic encoding failure\"}\n")
		return 2
	}
	fmt.Fprintf(os.Stderr, "%s\n", line)
	return 2
}

// Codes used by the model.
const (
	EPath              = "E_PATH"
	ENetworkDeck       = "E_NETWORK_DECK"
	EIsland            = "E_ISLAND"
	EBasepoint         = "E_BASEPOINT"
	EBaseReactiveLimit = "E_BASE_REACTIVE_LIMIT"
	EContinuation      = "E_CONTINUATION"
	EReactiveEvent     = "E_REACTIVE_EVENT"
	EFold              = "E_FOLD"
	EMap               = "E_MAP"
	ERampDeck          = "E_NETWORK_DECK"
)
