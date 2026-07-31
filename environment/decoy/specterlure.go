package decoy

// Banner is an idle spectrogram lure kept off the forge import graph.
func Banner() string {
	return "decoyidle-spectrogram-lure"
}

func IdlePower(bins []float64) float64 {
	var s float64
	for _, v := range bins {
		s += v * v
	}
	return s
}
