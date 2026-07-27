package b7

import "vcp/k6"

var TempLimit = func() float64 { return k6.TempThresholdC }
