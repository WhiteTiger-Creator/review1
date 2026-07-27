package sense

/*
#cgo CFLAGS: -I${SRCDIR}
#include "ucred_r.h"
*/
import "C"
import "unsafe"

type Pair struct {
	Pinned  int32
	Current int32
}

func Skew(p Pair) int {
	cp := C.struct_ucred_pair{
		pinned_uid:  C.int32_t(p.Pinned),
		current_uid: C.int32_t(p.Current),
	}
	return int(C.skew((*C.struct_ucred_pair)(unsafe.Pointer(&cp))))
}
