package output

import "fmt"

func Finalize(report Report) (Report, []byte, error) {
	_ = report
	return Report{}, nil, fmt.Errorf("canonical release encoding is not implemented")
}
