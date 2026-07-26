package main

func Estimate(imprs []Impression, numFeatures, numSlots int, dataDir string) ([]float64, []float64) {
	theta := make([]float64, numSlots)
	for p := 0; p < numSlots; p++ {
		theta[p] = 1.0
	}
	w := make([]float64, numFeatures)
	return theta, w
}
