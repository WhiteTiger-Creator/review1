package certify

import (
	"context"
	"fmt"
	"time"

	"orbit.local/sentinel/internal/output"
)

func Run(ctx context.Context, dbPath, apiOrigin, publishDir string, timeout time.Duration) (output.Report, error) {
	_, _, _, _, _ = ctx, dbPath, apiOrigin, publishDir, timeout
	return output.Report{}, fmt.Errorf("release certification is not implemented")
}
