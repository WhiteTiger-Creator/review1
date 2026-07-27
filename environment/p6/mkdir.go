package p6

import "os"

func Mkdir(p string) error { return os.MkdirAll(p, 0755) }
