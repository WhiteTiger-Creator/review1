package campaign

import (
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"

	"raidscrubctl/internal/config"
	"raidscrubctl/internal/model"
	"raidscrubctl/internal/publish"
)

type Options struct {
	Root              string
	Output            string
	Threshold         int
	Campaign          string
	Epoch             string
	Urgent            string
	ReadError         bool
	CorruptCheckpoint bool
}

type Report struct {
	ArraysKnown          int  `json:"arrays_known"`
	UUIDAssemblyClean    bool `json:"uuid_assembly_clean"`
	ConcurrentScrubsPeak int  `json:"concurrent_scrubs_peak"`
	UnsafeRepairs        int  `json:"unsafe_repairs"`
	SpareActivations     int  `json:"spare_activations"`
	ResumedScrubs        int  `json:"resumed_scrubs"`
	DuplicateAlerts      int  `json:"duplicate_alerts"`
	RecoveryAlerts       int  `json:"recovery_alerts"`
	LimitsRestored       bool `json:"limits_restored"`
	BudgetOK             bool `json:"budget_ok"`
	TriageOK             bool `json:"triage_ok"`
	AdjacencyOK          bool `json:"adjacency_ok"`
	QuorumOK             bool `json:"quorum_ok"`
	CheckpointOK         bool `json:"checkpoint_ok"`
	Accepted             bool `json:"accepted"`
}

type Event struct {
	Seq    int    `json:"seq"`
	Event  string `json:"event"`
	Array  string `json:"array"`
	UUID   string `json:"uuid"`
	Detail string `json:"detail"`
}

type ArrayStateEntry struct {
	Name            string `json:"name"`
	UUID            string `json:"uuid"`
	Level           string `json:"level"`
	Assembled       bool   `json:"assembled"`
	DegradedAllowed bool   `json:"degraded_allowed"`
	Bitmap          string `json:"bitmap"`
	SpareGroup      string `json:"spare_group"`
}

type State struct {
	Generation    string            `json:"generation"`
	Arrays        []ArrayStateEntry `json:"arrays"`
	LocksHeld     []string          `json:"locks_held"`
	SpeedLimitMin int               `json:"speed_limit_min"`
	SpeedLimitMax int               `json:"speed_limit_max"`
	ModelDigest   string            `json:"model_digest"`
}

type Result struct {
	Report Report
	Events []Event
	State  State
}

func sortedFlags(m map[string]bool) []string {
	out := make([]string, 0, len(m))
	for k := range m {
		out = append(out, k)
	}
	sort.Strings(out)
	return out
}

func Run(opt Options) (*Result, error) {
	if opt.Threshold <= 0 {
		opt.Threshold = 10
	}
	if opt.Campaign == "" {
		opt.Campaign = "standard"
	}
	if opt.Epoch == "" {
		opt.Epoch = "1"
	}
	if opt.CorruptCheckpoint {
		dir := filepath.Join(opt.Root, "var/lib/raid-scrub/checkpoints")
		_ = os.MkdirAll(dir, 0o755)
		_ = os.WriteFile(filepath.Join(dir, "data5.offset"), []byte("CORRUPT sector map unreadable\n"), 0o644)
	}
	settings, err := config.Load(opt.Root)
	if err != nil {
		return nil, err
	}
	if opt.ReadError {
		settings.ForceReadError = true
	}
	specs := model.Specs()

	res := &Result{}
	seq := 1
	add := func(event, array, uuid, detail string) {
		res.Events = append(res.Events, Event{Seq: seq, Event: event, Array: array, UUID: uuid, Detail: detail})
		seq++
	}

	known := 0
	uuidClean := true
	if settings.DeviceHostTouch {
		uuidClean = false
	}
	assembled := map[string]bool{}
	for _, spec := range specs {
		al := settings.ArrayByName(spec.Name)
		if al == nil {
			uuidClean = false
			continue
		}
		known++
		if al.PathBased || model.NormUUID(al.UUID) != model.NormUUID(spec.UUID) {
			uuidClean = false
		}
		if al.Foreign {
			uuidClean = false
			continue
		}
		assembled[spec.Name] = true
		add("assemble", spec.Name, spec.UUID, "uuid-assembly")
	}
	res.Report.ArraysKnown = known
	res.Report.UUIDAssemblyClean = uuidClean && known == 3 && !settings.DeviceHostTouch

	foreignExcluded := true
	foreignNames := make([]string, 0, len(settings.Arrays))
	for key := range settings.Arrays {
		foreignNames = append(foreignNames, key)
	}
	sort.Strings(foreignNames)
	for _, key := range foreignNames {
		al := settings.Arrays[key]
		if model.NormUUID(al.UUID) == model.NormUUID(model.ForeignUUID) || al.Foreign {
			if assembled[al.Name] {
				foreignExcluded = false
			} else {
				add("foreign_excluded", al.Name, al.UUID, "excluded")
			}
		}
	}
	for _, flag := range settings.ForeignFlags {
		add("foreign_excluded", "", "", filepath.Base(filepath.Dir(flag)))
	}
	if len(settings.ForeignFlags) == 0 && foreignExcluded {
		add("foreign_excluded", "foreign", model.ForeignUUID, "inventory-decoy")
	}

	res.Report.BudgetOK = settings.BudgetOK
	if settings.BudgetOK {
		add("budget_applied", "", "", fmt.Sprintf("ceiling_total=%d", settings.SpeedMax))
	} else {
		add("budget_rejected", "", "", "ceiling-sum-or-floor")
	}

	unsafe := 0
	bootOK := settings.BootDegraded == "yes"
	raid5Refuse := settings.RAID5Degraded == "refuse"
	if al := settings.ArrayByName("bootmirror"); al != nil {
		if !(bootOK && (strings.EqualFold(al.Auto, "yes") || al.SpareGroup == "boot")) {
			bootOK = false
		}
	} else {
		bootOK = false
	}
	if al := settings.ArrayByName("data5"); al != nil {
		autoOK := al.Auto == "-all" || strings.Contains(strings.ToLower(al.Raw), "refuse-degraded")
		if !(raid5Refuse && autoOK) {
			unsafe++
			add("repair_refused", "data5", specs[1].UUID, "unsafe-degraded-policy-missing")
		}
	} else {
		unsafe++
	}

	bitmapOK := true
	for _, spec := range specs {
		al := settings.ArrayByName(spec.Name)
		if al == nil || al.Bitmap != spec.Bitmap {
			bitmapOK = false
		}
	}

	spareAct := 0
	triageOK := false
	urgent := settings.UrgentTarget(opt.Urgent)
	urgentIdx := -1
	for i := range specs {
		if specs[i].Name == urgent {
			urgentIdx = i
			break
		}
	}
	if urgentIdx < 0 {
		add("triage_selected", "", "", "no-urgent-array")
	} else {
		us := specs[urgentIdx]
		add("triage_selected", us.Name, us.UUID, "spare-group="+us.SpareGroup)
		al := settings.ArrayByName(us.Name)
		rel, eligible := settings.SpareEligible(us.SpareGroup)
		if eligible && al != nil && al.SpareGroup == us.SpareGroup && assembled[us.Name] {
			spareAct = 1
			triageOK = true
			add("spare_activated", us.Name, us.UUID, rel)
		} else {
			add("spare_withheld", us.Name, us.UUID, "group-mismatch-or-missing")
		}
	}
	res.Report.SpareActivations = spareAct
	res.Report.TriageOK = triageOK

	days := map[int]int{}
	peak := 0
	for _, spec := range specs {
		d, ok := settings.TimerDays[spec.Name]
		if !ok || d < spec.DOMMin || d > spec.DOMMax {
			peak = 3
			continue
		}
		days[d]++
		if days[d] > peak {
			peak = days[d]
		}
	}
	if peak == 0 {
		peak = 3
	}
	if !settings.CalendarAligned {
		peak = 3
	}
	res.Report.ConcurrentScrubsPeak = peak
	res.Report.AdjacencyOK = settings.AdjacencyOK

	for _, name := range sortedFlags(settings.CheckpointQuar) {
		add("checkpoint_quarantined", name, "", "set-aside")
	}
	for _, name := range sortedFlags(settings.CheckpointCorrupt) {
		add("checkpoint_rejected", name, "", "corrupt-marker")
	}
	res.Report.CheckpointOK = settings.CheckpointOK

	quorumAllows := settings.QuorumAllows(opt.Epoch)
	res.Report.QuorumOK = settings.Authorize[model.NormUUID(specs[1].UUID)] && quorumAllows

	resumed := 0
	mismatches := map[string]int{
		"bootmirror": 2,
		"data5":      14,
		"fast10":     0,
	}
	locks := map[string]bool{}
	for _, spec := range specs {
		if !assembled[spec.Name] {
			continue
		}
		if settings.SyncAction[spec.Name] == "rebuild" {
			if settings.RebuildSkip[spec.Name] {
				add("scrub_skipped_rebuild", spec.Name, spec.UUID, "rebuild")
				continue
			}
		}
		locks[spec.Name] = true
		writeLock(opt.Root, spec.Name, true)
		if off, ok := settings.Checkpoints[spec.Name]; ok && off > 0 {
			resumed++
			add("scrub_resumed", spec.Name, spec.UUID, fmt.Sprintf("offset=%d", off))
		} else {
			add("scrub_started", spec.Name, spec.UUID, fmt.Sprintf("dom=%d", settings.TimerDays[spec.Name]))
		}
		mm := mismatches[spec.Name]
		add("mismatch_observed", spec.Name, spec.UUID, fmt.Sprintf("count=%d", mm))
		if opt.Campaign == "monitor" {
			locks[spec.Name] = false
			writeLock(opt.Root, spec.Name, false)
			continue
		}
		if mm > opt.Threshold {
			if !settings.Authorize[model.NormUUID(spec.UUID)] {
				unsafe++
				add("repair_refused", spec.Name, spec.UUID, "unauthorized")
				add("lock_released", spec.Name, spec.UUID, "failure")
				locks[spec.Name] = false
				writeLock(opt.Root, spec.Name, false)
				continue
			}
			if !quorumAllows {
				unsafe++
				add("quorum_denied", spec.Name, spec.UUID, "epoch="+opt.Epoch)
				add("lock_released", spec.Name, spec.UUID, "failure")
				locks[spec.Name] = false
				writeLock(opt.Root, spec.Name, false)
				continue
			}
			add("repair_authorized", spec.Name, spec.UUID, "authorized")
			if settings.ForceReadError && spec.Name == "data5" {
				add("read_error", spec.Name, spec.UUID, "stopped")
				add("lock_released", spec.Name, spec.UUID, "failure")
				locks[spec.Name] = false
				writeLock(opt.Root, spec.Name, false)
				continue
			}
		}
		locks[spec.Name] = false
		writeLock(opt.Root, spec.Name, false)
	}
	res.Report.ResumedScrubs = resumed
	res.Report.UnsafeRepairs = unsafe

	dup := 0
	rec := 0
	if settings.NotifyOK {
		_ = os.MkdirAll(filepath.Join(opt.Root, "var/lib/raid-scrub/alerts"), 0o755)
		_ = os.WriteFile(filepath.Join(opt.Root, "var/lib/raid-scrub/alerts/last-state.json"), []byte(`{"state":"degraded","array":"bootmirror"}`+"\n"), 0o644)
		add("alert_degraded", "bootmirror", specs[0].UUID, "captured")
		add("alert_recovery", "bootmirror", specs[0].UUID, "recovered")
		rec = 1
		dup = 0
	} else {
		add("alert_degraded", "bootmirror", specs[0].UUID, "raw")
		add("alert_degraded", "bootmirror", specs[0].UUID, "duplicate")
		dup = 1
		if settings.NotifyNoSerial {
			add("alert_recovery", "bootmirror", specs[0].UUID, "recovered")
			rec = 1
		}
	}
	res.Report.DuplicateAlerts = dup
	res.Report.RecoveryAlerts = rec

	limitsOK := settings.SpeedMin == 1000 && settings.SpeedMax == 200000
	if limitsOK {
		_ = os.MkdirAll(filepath.Join(opt.Root, "var/lib/raid-scrub/state"), 0o755)
		_ = os.WriteFile(filepath.Join(opt.Root, "var/lib/raid-scrub/state/speed_limit_min"), []byte("1000\n"), 0o644)
		_ = os.WriteFile(filepath.Join(opt.Root, "var/lib/raid-scrub/state/speed_limit_max"), []byte("200000\n"), 0o644)
		add("limits_restored", "", "", "1000:200000")
	}
	res.Report.LimitsRestored = limitsOK

	held := []string{}
	for name, on := range locks {
		if on {
			held = append(held, name)
		}
	}
	sort.Strings(held)

	structuralOK := settings.ConfDComplete && settings.CalendarAligned && settings.RebuildSkipReady && settings.HelperSyntaxOK
	accepted := res.Report.ArraysKnown == 3 &&
		res.Report.UUIDAssemblyClean &&
		res.Report.ConcurrentScrubsPeak == 1 &&
		res.Report.UnsafeRepairs == 0 &&
		res.Report.SpareActivations == 1 &&
		res.Report.ResumedScrubs == 1 &&
		res.Report.DuplicateAlerts == 0 &&
		res.Report.RecoveryAlerts == 1 &&
		res.Report.LimitsRestored &&
		res.Report.BudgetOK &&
		res.Report.TriageOK &&
		res.Report.AdjacencyOK &&
		res.Report.QuorumOK &&
		res.Report.CheckpointOK &&
		bitmapOK &&
		bootOK &&
		foreignExcluded &&
		len(held) == 0 &&
		structuralOK
	res.Report.Accepted = accepted

	entries := []ArrayStateEntry{}
	for _, spec := range specs {
		al := settings.ArrayByName(spec.Name)
		e := ArrayStateEntry{
			Name:            spec.Name,
			UUID:            spec.UUID,
			Level:           spec.Level,
			Assembled:       assembled[spec.Name],
			DegradedAllowed: spec.Name == "bootmirror" && bootOK,
			Bitmap:          spec.Bitmap,
			SpareGroup:      spec.SpareGroup,
		}
		if al != nil && al.Bitmap != "" {
			e.Bitmap = al.Bitmap
		}
		if al != nil && al.SpareGroup != "" {
			e.SpareGroup = al.SpareGroup
		}
		entries = append(entries, e)
	}
	sort.Slice(entries, func(i, j int) bool { return entries[i].UUID < entries[j].UUID })

	genPayload := strings.Join([]string{
		opt.Epoch,
		strconv.Itoa(opt.Threshold),
		opt.Campaign,
		urgent,
		model.Digest(),
		fmt.Sprintf("%v", accepted),
		fmt.Sprintf("%d", known),
	}, "|")
	sum := sha256.Sum256([]byte(genPayload))
	res.State = State{
		Generation:    hex.EncodeToString(sum[:8]),
		Arrays:        entries,
		LocksHeld:     held,
		SpeedLimitMin: 0,
		SpeedLimitMax: 0,
		ModelDigest:   model.Digest(),
	}
	if limitsOK {
		res.State.SpeedLimitMin = 1000
		res.State.SpeedLimitMax = 200000
	}

	if err := writeOutputs(opt.Output, res); err != nil {
		return nil, err
	}
	return res, nil
}

func writeLock(root, name string, hold bool) {
	dir := filepath.Join(root, "var/lib/raid-scrub/locks")
	_ = os.MkdirAll(dir, 0o755)
	path := filepath.Join(dir, name+".lock")
	if hold {
		_ = os.WriteFile(path, []byte("held\n"), 0o644)
	} else {
		_ = os.Remove(path)
	}
}

func writeOutputs(out string, res *Result) error {
	if err := publish.AtomicJSON(filepath.Join(out, "raid-report.json"), res.Report); err != nil {
		return err
	}
	lines := make([]string, 0, len(res.Events))
	for _, ev := range res.Events {
		b, _ := json.Marshal(ev)
		lines = append(lines, string(b))
	}
	if err := publish.AtomicLines(filepath.Join(out, "scrub-events.jsonl"), lines); err != nil {
		return err
	}
	return publish.AtomicJSON(filepath.Join(out, "array-state.json"), res.State)
}
