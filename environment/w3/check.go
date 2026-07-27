package w3

import (
	"encoding/json"
	"fmt"
	"os"
)

func Check(v, nest, out string) (string, error) {
	_ = v
	_ = nest
	if _, e := os.Stat(out); e != nil {
		return "pending", nil
	}
	return "settled", nil
}

func Status(v, n, o string) error {
	s, e := Check(v, n, o)
	if e != nil {
		return e
	}
	return json.NewEncoder(stdout{}).Encode(map[string]string{"state": s})
}

type stdout struct{}

func (stdout) Write(b []byte) (int, error) { return fmt.Print(string(b)) }
