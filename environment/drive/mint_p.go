package drive

import "gwc/hearth"

func MintCookie(path string, gen uint64, armEpoch uint64) string {
	return hearth.Mint(path, gen, armEpoch)
}
