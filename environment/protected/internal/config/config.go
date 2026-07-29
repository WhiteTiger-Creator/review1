package config

import (
	"bufio"
	"fmt"
	"os"
	"os/exec"
	"path/filepath"
	"regexp"
	"sort"
	"strconv"
	"strings"

	"raidscrubctl/internal/model"
)

type ArrayLine struct {
	Name       string
	UUID       string
	SpareGroup string
	Bitmap     string
	Auto       string
	PathBased  bool
	Foreign    bool
	Raw        string
	Source     string
}

type Settings struct {
	Root              string
	Arrays            map[string]*ArrayLine
	ArraysByUUID      map[string]*ArrayLine
	DeviceHostTouch   bool
	BootDegraded      string
	RAID5Degraded     string
	SpareGroups       map[string][]string
	TimerDays         map[string]int
	Checkpoints       map[string]int64
	CheckpointCorrupt map[string]bool
	CheckpointQuar    map[string]bool
	SpeedMin          int
	SpeedMax          int
	Budgets           map[string]int
	BudgetPresent     bool
	UrgentArray       string
	UrgencyPresent    bool
	QuorumEpochs      map[string]bool
	QuorumPresent     bool
	Authorize         map[string]bool
	NotifyOK          bool
	NotifySuppress    bool
	NotifyNoSerial    bool
	NotifyCaptures    bool
	RebuildSkip       map[string]bool
	SyncAction        map[string]string
	ForeignFlags      []string
	HelperSyntaxOK    bool
	ConfDComplete     bool
	CalendarAligned   bool
	AdjacencyOK       bool
	BudgetOK          bool
	CheckpointOK      bool
	RebuildSkipReady  bool
	MdadmFiles        []string
	ForceReadError    bool
	InactiveForeign   bool
}

func Load(root string) (*Settings, error) {
	s := &Settings{
		Root:              root,
		Arrays:            map[string]*ArrayLine{},
		ArraysByUUID:      map[string]*ArrayLine{},
		SpareGroups:       map[string][]string{},
		TimerDays:         map[string]int{},
		Checkpoints:       map[string]int64{},
		CheckpointCorrupt: map[string]bool{},
		CheckpointQuar:    map[string]bool{},
		Budgets:           map[string]int{},
		QuorumEpochs:      map[string]bool{},
		Authorize:         map[string]bool{},
		RebuildSkip:       map[string]bool{},
		SyncAction:        map[string]string{},
		SpeedMin:          -1,
		SpeedMax:          -1,
	}
	if err := s.loadMdadm(); err != nil {
		return nil, err
	}
	s.loadDefaults()
	s.loadSpares()
	s.loadTimers()
	s.loadCheckpoints()
	s.loadLimits()
	s.loadBudget()
	s.loadUrgency()
	s.loadQuorum()
	s.loadAuthorize()
	s.loadNotify()
	s.loadState()
	s.loadForeignFlags()
	s.validateHelpers()
	s.computeStructural()
	return s, nil
}

func (s *Settings) loadMdadm() error {
	paths := []string{filepath.Join(s.Root, "etc/mdadm/mdadm.conf")}
	drop := filepath.Join(s.Root, "etc/mdadm/mdadm.conf.d")
	entries, _ := os.ReadDir(drop)
	var names []string
	for _, e := range entries {
		if !e.IsDir() && strings.HasSuffix(e.Name(), ".conf") {
			names = append(names, e.Name())
		}
	}
	sort.Strings(names)
	for _, n := range names {
		paths = append(paths, filepath.Join(drop, n))
	}
	s.MdadmFiles = paths
	for _, path := range paths {
		body, err := os.ReadFile(path)
		if err != nil {
			if os.IsNotExist(err) && strings.HasSuffix(path, "mdadm.conf") {
				continue
			}
			return err
		}
		sc := bufio.NewScanner(strings.NewReader(string(body)))
		for sc.Scan() {
			line := strings.TrimSpace(sc.Text())
			if line == "" || strings.HasPrefix(line, "#") {
				continue
			}
			upper := strings.ToUpper(line)
			if strings.HasPrefix(upper, "DEVICE") {
				if strings.Contains(line, "/dev/sd") || strings.Contains(line, "/dev/nvme") || strings.Contains(line, "/dev/vd") {
					s.DeviceHostTouch = true
				}
				continue
			}
			if strings.HasPrefix(upper, "ARRAY") {
				al := parseArrayLine(line, path)
				key := al.Name
				if key == "" {
					key = al.UUID
				}
				s.Arrays[key] = al
				if al.UUID != "" {
					s.ArraysByUUID[model.NormUUID(al.UUID)] = al
				}
				if model.NormUUID(al.UUID) == model.NormUUID(model.ForeignUUID) {
					s.InactiveForeign = true
				}
			}
		}
	}
	return nil
}

var (
	reUUID   = regexp.MustCompile(`(?i)\bUUID=([0-9a-f-]+)`)
	reSpare  = regexp.MustCompile(`(?i)\bspare-group=([^\s]+)`)
	reBitmap = regexp.MustCompile(`(?i)\bbitmap=([^\s]+)`)
	reAuto   = regexp.MustCompile(`(?i)\bAUTO=([^\s]+)`)
	reName   = regexp.MustCompile(`(?i)/dev/md[/=]?([A-Za-z0-9_-]+)`)
)

func parseArrayLine(line, source string) *ArrayLine {
	al := &ArrayLine{Raw: line, Source: source}
	if m := reUUID.FindStringSubmatch(line); len(m) == 2 {
		al.UUID = model.NormUUID(m[1])
	} else {
		al.PathBased = true
	}
	if m := reSpare.FindStringSubmatch(line); len(m) == 2 {
		al.SpareGroup = strings.ToLower(m[1])
	}
	if m := reBitmap.FindStringSubmatch(line); len(m) == 2 {
		al.Bitmap = strings.ToLower(m[1])
	}
	if m := reAuto.FindStringSubmatch(line); len(m) == 2 {
		al.Auto = m[1]
	}
	if m := reName.FindStringSubmatch(line); len(m) == 2 {
		al.Name = strings.ToLower(m[1])
	}
	if strings.Contains(strings.ToLower(line), "foreign") {
		al.Foreign = true
	}
	return al
}

func (s *Settings) loadDefaults() {
	path := filepath.Join(s.Root, "etc/default/mdadm")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "BOOT_DEGRADED=") {
			s.BootDegraded = strings.Trim(strings.TrimPrefix(line, "BOOT_DEGRADED="), `"'`)
		}
		if strings.HasPrefix(line, "RAID5_DEGRADED=") {
			s.RAID5Degraded = strings.Trim(strings.TrimPrefix(line, "RAID5_DEGRADED="), `"'`)
		}
	}
}

func (s *Settings) loadSpares() {
	path := filepath.Join(s.Root, "etc/mdadm/spare-groups.conf")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		group := strings.ToLower(strings.TrimSpace(parts[0]))
		spath := strings.TrimSpace(parts[1])
		s.SpareGroups[group] = append(s.SpareGroups[group], spath)
	}
}

// SpareEligible returns the first declared spare whose declared path actually
// resides inside the directory named for the group and exists on disk.
func (s *Settings) SpareEligible(group string) (string, bool) {
	decl := append([]string{}, s.SpareGroups[group]...)
	sort.Strings(decl)
	for _, rel := range decl {
		abs := rel
		if !filepath.IsAbs(abs) {
			abs = filepath.Join(s.Root, rel)
		}
		slashed := filepath.ToSlash(abs)
		if filepath.Base(filepath.Dir(slashed)) != group {
			continue
		}
		st, err := os.Stat(abs)
		if err != nil || st.IsDir() {
			continue
		}
		return rel, true
	}
	return "", false
}

var reOnCal = regexp.MustCompile(`(?i)OnCalendar=\*-\*-([1-9]|[12][0-9]|3[01])\s+03:00:00`)

func (s *Settings) loadTimers() {
	dir := filepath.Join(s.Root, "etc/systemd/system")
	_ = filepath.WalkDir(dir, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		if !strings.HasSuffix(d.Name(), ".timer") {
			return nil
		}
		body, err := os.ReadFile(path)
		if err != nil {
			return nil
		}
		text := string(body)
		day := 0
		if m := reOnCal.FindStringSubmatch(text); len(m) == 2 {
			day, _ = strconv.Atoi(m[1])
		}
		name := ""
		lower := strings.ToLower(d.Name() + " " + text)
		for _, spec := range model.Specs() {
			if strings.Contains(lower, spec.Name) {
				name = spec.Name
				break
			}
		}
		if name != "" && day > 0 {
			s.TimerDays[name] = day
		}
		return nil
	})
}

func (s *Settings) loadCheckpoints() {
	dir := filepath.Join(s.Root, "var/lib/raid-scrub/checkpoints")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if e.IsDir() {
			continue
		}
		base := e.Name()
		if strings.HasSuffix(base, ".offset.bad") {
			s.CheckpointQuar[strings.TrimSuffix(base, ".offset.bad")] = true
			continue
		}
		if !strings.HasSuffix(base, ".offset") {
			continue
		}
		array := strings.TrimSuffix(base, ".offset")
		body, err := os.ReadFile(filepath.Join(dir, base))
		if err != nil {
			continue
		}
		text := string(body)
		if strings.Contains(text, "CORRUPT") {
			s.CheckpointCorrupt[array] = true
			continue
		}
		v, err := strconv.ParseInt(strings.TrimSpace(text), 10, 64)
		if err == nil {
			s.Checkpoints[array] = v
		}
	}
}

func (s *Settings) loadLimits() {
	path := filepath.Join(s.Root, "etc/raid-scrub/speed-limits.conf")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "speed_limit_min=") {
			s.SpeedMin, _ = strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(line, "speed_limit_min=")))
		}
		if strings.HasPrefix(line, "speed_limit_max=") {
			s.SpeedMax, _ = strconv.Atoi(strings.TrimSpace(strings.TrimPrefix(line, "speed_limit_max=")))
		}
	}
}

func (s *Settings) loadBudget() {
	path := filepath.Join(s.Root, "etc/raid-scrub/io-budget.conf")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	s.BudgetPresent = true
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		name := strings.ToLower(strings.TrimSpace(parts[0]))
		v, err := strconv.Atoi(strings.TrimSpace(parts[1]))
		if err != nil {
			continue
		}
		s.Budgets[name] = v
	}
}

func (s *Settings) loadUrgency() {
	path := filepath.Join(s.Root, "etc/raid-scrub/urgency.conf")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	s.UrgencyPresent = true
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "urgent=") {
			s.UrgentArray = strings.ToLower(strings.TrimSpace(strings.TrimPrefix(line, "urgent=")))
		}
	}
}

func (s *Settings) loadQuorum() {
	path := filepath.Join(s.Root, "etc/raid-scrub/repair.quorum")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	s.QuorumPresent = true
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		if strings.HasPrefix(line, "epoch=") {
			s.QuorumEpochs[strings.TrimSpace(strings.TrimPrefix(line, "epoch="))] = true
		}
	}
}

// QuorumAllows reports whether the change-board file authorizes repair work for
// the requested epoch. A star entry authorizes every epoch.
func (s *Settings) QuorumAllows(epoch string) bool {
	if !s.QuorumPresent {
		return false
	}
	if s.QuorumEpochs["*"] {
		return true
	}
	return s.QuorumEpochs[strings.TrimSpace(epoch)]
}

func (s *Settings) loadAuthorize() {
	path := filepath.Join(s.Root, "etc/raid-scrub/repair.authorize")
	body, err := os.ReadFile(path)
	if err != nil {
		return
	}
	sc := bufio.NewScanner(strings.NewReader(string(body)))
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		s.Authorize[model.NormUUID(line)] = true
	}
}

func (s *Settings) loadNotify() {
	path := filepath.Join(s.Root, "usr/local/lib/raid-scrub/notify.sh")
	body, err := os.ReadFile(path)
	if err != nil {
		s.HelperSyntaxOK = false
		return
	}
	text := string(body)
	cmd := exec.Command("bash", "-n", path)
	if err := cmd.Run(); err != nil {
		s.HelperSyntaxOK = false
	} else {
		s.HelperSyntaxOK = true
	}
	s.NotifyCaptures = strings.Contains(text, "last-state.json")
	s.NotifySuppress = strings.Contains(text, "suppress") || strings.Contains(text, "duplicate") || strings.Contains(text, "seen_degraded")
	s.NotifyNoSerial = !strings.Contains(text, "serial=") && strings.Contains(text, "recovered")
	s.NotifyOK = s.HelperSyntaxOK && s.NotifyCaptures && s.NotifySuppress && s.NotifyNoSerial
}

func (s *Settings) loadState() {
	dir := filepath.Join(s.Root, "var/lib/raid-scrub/state")
	for _, spec := range model.Specs() {
		p := filepath.Join(dir, spec.Name, "sync_action")
		body, err := os.ReadFile(p)
		if err == nil {
			s.SyncAction[spec.Name] = strings.TrimSpace(string(body))
		}
		helper := filepath.Join(s.Root, "usr/local/lib/raid-scrub", "scrub-"+spec.Name+".sh")
		b, err := os.ReadFile(helper)
		if err == nil && strings.Contains(string(b), "rebuild") {
			s.RebuildSkip[spec.Name] = true
		}
		svc := filepath.Join(s.Root, "etc/systemd/system", "raid-scrub-"+spec.Name+".service")
		sb, err := os.ReadFile(svc)
		if err == nil && strings.Contains(string(sb), "rebuild") {
			s.RebuildSkip[spec.Name] = true
		}
	}
	if _, err := os.Stat(filepath.Join(s.Root, "var/lib/raid-scrub/inject-read-error")); err == nil {
		s.ForceReadError = true
	}
}

func (s *Settings) loadForeignFlags() {
	root := filepath.Join(s.Root, "var/lib/raid-scrub/members")
	_ = filepath.WalkDir(root, func(path string, d os.DirEntry, err error) error {
		if err != nil || d.IsDir() {
			return nil
		}
		if d.Name() == "foreign.flag" {
			s.ForeignFlags = append(s.ForeignFlags, path)
		}
		return nil
	})
	sort.Strings(s.ForeignFlags)
}

func (s *Settings) validateHelpers() {
	dir := filepath.Join(s.Root, "usr/local/lib/raid-scrub")
	entries, err := os.ReadDir(dir)
	if err != nil {
		return
	}
	for _, e := range entries {
		if e.IsDir() || !strings.HasSuffix(e.Name(), ".sh") {
			continue
		}
		path := filepath.Join(dir, e.Name())
		if err := exec.Command("bash", "-n", path).Run(); err != nil {
			s.HelperSyntaxOK = false
			return
		}
	}
}

func (s *Settings) ArrayByName(name string) *ArrayLine {
	if al, ok := s.Arrays[name]; ok {
		return al
	}
	for _, al := range s.Arrays {
		if al.Name == name {
			return al
		}
	}
	for _, spec := range model.Specs() {
		if spec.Name != name {
			continue
		}
		if al, ok := s.ArraysByUUID[model.NormUUID(spec.UUID)]; ok {
			return al
		}
	}
	return nil
}

// UrgentTarget resolves the array that spare triage is allowed to repair. The
// override wins over the staged urgency declaration.
func (s *Settings) UrgentTarget(override string) string {
	if v := strings.ToLower(strings.TrimSpace(override)); v != "" {
		return v
	}
	return s.UrgentArray
}

func DescribeLoadError(err error) string {
	return fmt.Sprintf("config load: %v", err)
}

func (s *Settings) computeStructural() {
	confd := 0
	for _, spec := range model.Specs() {
		al := s.ArrayByName(spec.Name)
		if al != nil && strings.Contains(filepath.ToSlash(al.Source), "/mdadm.conf.d/") {
			confd++
		}
	}
	s.ConfDComplete = confd == len(model.Specs())

	aligned := true
	days := []int{}
	for _, spec := range model.Specs() {
		d, ok := s.TimerDays[spec.Name]
		if !ok || d < spec.DOMMin || d > spec.DOMMax {
			aligned = false
			continue
		}
		days = append(days, d)
	}
	s.CalendarAligned = aligned && len(days) == len(model.Specs())

	adjacency := s.CalendarAligned
	for i := 0; i < len(days); i++ {
		for j := i + 1; j < len(days); j++ {
			gap := days[i] - days[j]
			if gap < 0 {
				gap = -gap
			}
			if gap < 7 {
				adjacency = false
			}
		}
	}
	s.AdjacencyOK = adjacency

	budgetOK := s.BudgetPresent && len(s.Budgets) == len(model.Specs())
	total := 0
	for _, spec := range model.Specs() {
		v, ok := s.Budgets[spec.Name]
		if !ok || v < spec.FloorKib {
			budgetOK = false
		}
		total += v
	}
	if s.SpeedMax <= 0 || total != s.SpeedMax {
		budgetOK = false
	}
	s.BudgetOK = budgetOK

	s.CheckpointOK = len(s.CheckpointCorrupt) == 0

	ready := true
	for _, spec := range model.Specs() {
		if !s.RebuildSkip[spec.Name] {
			ready = false
			break
		}
	}
	s.RebuildSkipReady = ready
}
