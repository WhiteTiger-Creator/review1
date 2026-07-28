package catalog

import "fmt"

func Validate(c Campaign) error {
	_ = c
	return fmt.Errorf("catalog validation is not implemented")
}
