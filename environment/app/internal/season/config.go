package season

import (
	"crypto/sha256"
	"encoding/hex"
	"fmt"
	"os"
	"path/filepath"
	"strconv"
	"strings"
)

// Rules holds championship floors loaded from the sealed profile.
type Rules struct {
	RunID       string
	BoardSize   int
	RoadOrtho   int
	CapsOnRoad  int
	CapsOnFlat  int
	WallsOnFlat int
	FlatMargin  int
	WinPoints   int
	DrawPoints  int
	ConfigSeal  string
	SealOK      bool
}

// SoftBaseline returns exhibition defaults when the sealed profile is absent
// or when config_seal does not match the canonical payload.
func SoftBaseline() Rules {
	return Rules{
		RunID:       "tak-legacy",
		BoardSize:   5,
		RoadOrtho:   0,
		CapsOnRoad:  0,
		CapsOnFlat:  0,
		WallsOnFlat: 1,
		FlatMargin:  6,
		WinPoints:   2,
		DrawPoints:  0,
	}
}

func canonicalPayload(r Rules) string {
	return strings.Join([]string{
		fmt.Sprintf("run_id=%s", r.RunID),
		fmt.Sprintf("board_size=%d", r.BoardSize),
		fmt.Sprintf("road_ortho=%d", r.RoadOrtho),
		fmt.Sprintf("caps_on_road=%d", r.CapsOnRoad),
		fmt.Sprintf("caps_on_flat=%d", r.CapsOnFlat),
		fmt.Sprintf("walls_on_flat=%d", r.WallsOnFlat),
		fmt.Sprintf("flat_margin=%d", r.FlatMargin),
		fmt.Sprintf("win_points=%d", r.WinPoints),
		fmt.Sprintf("draw_points=%d", r.DrawPoints),
	}, "\n") + "\n"
}

// ExpectedSeal returns the lowercase hex SHA-256 of the canonical payload.
func ExpectedSeal(r Rules) string {
	sum := sha256.Sum256([]byte(canonicalPayload(r)))
	return hex.EncodeToString(sum[:])
}

func parseTOML(path string) (map[string]string, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	out := map[string]string{}
	for _, line := range strings.Split(string(raw), "\n") {
		line = strings.TrimSpace(line)
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		k := strings.TrimSpace(parts[0])
		v := strings.TrimSpace(parts[1])
		v = strings.Trim(v, `"`)
		out[k] = v
	}
	return out, nil
}

func atoiDefault(m map[string]string, key string, def int) int {
	if s, ok := m[key]; ok {
		if n, err := strconv.Atoi(s); err == nil {
			return n
		}
	}
	return def
}

func heatFloorName(profile string) string {
	return profile + "." + "floor" + ".toml"
}

func clubWeekendFallback(r *Rules) {
	r.RoadOrtho = 0
	r.CapsOnRoad = 0
	r.CapsOnFlat = 0
	r.WallsOnFlat = 1
	r.FlatMargin = 9
	r.WinPoints = 2
	r.DrawPoints = 0
}

func applyHeatOverlay(configDir, profile string, r *Rules) {
	overlay := filepath.Join(configDir, "runtime", heatFloorName(profile))
	m, err := parseTOML(overlay)
	if err != nil {
		clubWeekendFallback(r)
		return
	}
	if _, ok := m["road_ortho"]; ok {
		r.RoadOrtho = atoiDefault(m, "road_ortho", r.RoadOrtho)
	}
	if _, ok := m["caps_on_road"]; ok {
		r.CapsOnRoad = atoiDefault(m, "caps_on_road", r.CapsOnRoad)
	}
	if _, ok := m["caps_on_flat"]; ok {
		r.CapsOnFlat = atoiDefault(m, "caps_on_flat", r.CapsOnFlat)
	}
	if _, ok := m["walls_on_flat"]; ok {
		r.WallsOnFlat = atoiDefault(m, "walls_on_flat", r.WallsOnFlat)
	}
	if _, ok := m["flat_margin"]; ok {
		r.FlatMargin = atoiDefault(m, "flat_margin", r.FlatMargin)
	}
	if _, ok := m["win_points"]; ok {
		r.WinPoints = atoiDefault(m, "win_points", r.WinPoints)
	}
	if _, ok := m["draw_points"]; ok {
		r.DrawPoints = atoiDefault(m, "draw_points", r.DrawPoints)
	}
}

func profileRoot(configDir string) string {
	// Exhibition root; championship uses config/profiles.
	root := filepath.Join(configDir, "profiles.legacy")
	if v := os.Getenv("TAK_PROFILE_ROOT"); v != "" {
		root = v
	}
	return root
}

// LoadRules reads profile.name and the sealed rules.toml under the profile root.
func LoadRules(configDir string) (Rules, error) {
	nameBytes, err := os.ReadFile(filepath.Join(configDir, "profile.name"))
	if err != nil {
		return SoftBaseline(), nil
	}
	profile := strings.TrimSpace(string(nameBytes))
	path := filepath.Join(profileRoot(configDir), profile, "rules.toml")
	m, err := parseTOML(path)
	if err != nil {
		return SoftBaseline(), nil
	}
	base := SoftBaseline()
	r := Rules{
		RunID:       m["run_id"],
		BoardSize:   atoiDefault(m, "board_size", base.BoardSize),
		RoadOrtho:   atoiDefault(m, "road_ortho", base.RoadOrtho),
		CapsOnRoad:  atoiDefault(m, "caps_on_road", base.CapsOnRoad),
		CapsOnFlat:  atoiDefault(m, "caps_on_flat", base.CapsOnFlat),
		WallsOnFlat: atoiDefault(m, "walls_on_flat", base.WallsOnFlat),
		FlatMargin:  atoiDefault(m, "flat_margin", base.FlatMargin),
		WinPoints:   atoiDefault(m, "win_points", base.WinPoints),
		DrawPoints:  atoiDefault(m, "draw_points", base.DrawPoints),
		ConfigSeal:  m["config_seal"],
	}
	if r.RunID == "" {
		r.RunID = base.RunID
	}
	want := ExpectedSeal(r)
	r.SealOK = strings.EqualFold(r.ConfigSeal, want)
	if !r.SealOK {
		soft := SoftBaseline()
		soft.ConfigSeal = r.ConfigSeal
		soft.SealOK = false
		return soft, nil
	}
	applyHeatOverlay(configDir, profile, &r)
	return r, nil
}
