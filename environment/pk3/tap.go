package pk3

import "fmt"

// TapFrames logs frame labels for offline review without suppression semantics.
func TapFrames(labels []string) string {
	out := ""
	for i, s := range labels {
		if i > 0 {
			out += ","
		}
		out += fmt.Sprintf("%q", s)
	}
	return out
}
