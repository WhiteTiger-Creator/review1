// Package cli implements the privhelper command-line surface.
package cli

import (
	"bufio"
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"os"
	"path/filepath"
	"strings"

	"privhelper/internal/canonical"
	"privhelper/internal/dispatch"
	"privhelper/internal/fsutil"
	"privhelper/internal/helper"
	"privhelper/internal/journal"
	"privhelper/internal/ledger"
	"privhelper/internal/manifest"
	"privhelper/internal/model"
	"privhelper/internal/reconcile"
	"privhelper/internal/recovery"
)

// Run dispatches a CLI invocation. args excludes the program name.
func Run(args []string) error {
	if len(args) == 0 {
		return fmt.Errorf("usage: privhelper <command> [flags]")
	}
	cmd, rest := args[0], args[1:]
	p := model.NewPaths()

	switch cmd {
	case "reset":
		return cmdReset(p, rest)
	case "dispatch":
		return cmdDispatch(p, rest)
	case "dispatch-batch":
		return cmdDispatchBatch(p, rest)
	case "manifest-install":
		return cmdManifestInstall(p, rest)
	case "recover":
		return cmdRecover(p, rest)
	case "resolved-helpers":
		return cmdResolvedHelpers(p, rest)
	case "journal-export":
		return cmdJournalExport(p, rest)
	case "decisions-export":
		return cmdDecisionsExport(p, rest)
	case "effects-export":
		return cmdEffectsExport(p, rest)
	case "reconcile":
		return cmdReconcile(p, rest)
	case "selftest":
		return cmdSelftest(p, rest)
	default:
		return fmt.Errorf("unknown command %q", cmd)
	}
}

// ---- reset ---------------------------------------------------------------

func cmdReset(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("reset", flag.ContinueOnError)
	scenario := fs.String("scenario", "", "scenario to reset (ops-seal)")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *scenario != "ops-seal" {
		return fmt.Errorf("reset only supports --scenario ops-seal")
	}
	return doReset(p)
}

func doReset(p model.Paths) error {
	// Recreate var/privhelper cleanly.
	if err := fsutil.RemoveAll(p.VarDir()); err != nil {
		return err
	}
	if err := fsutil.EnsureDir(p.VarDir()); err != nil {
		return err
	}
	// Clean reports.
	if err := fsutil.RemoveAll(p.Reports()); err != nil {
		return err
	}
	if err := fsutil.EnsureDir(p.Reports()); err != nil {
		return err
	}

	// Reinstall trusted helpers from share into libexec.
	if err := fsutil.RemoveAll(p.Libexec()); err != nil {
		return err
	}
	if err := fsutil.EnsureDir(p.Libexec()); err != nil {
		return err
	}
	if err := copyGlob(p.ShareHelpers(), "*.py", p.Libexec(), 0o755); err != nil {
		return fmt.Errorf("reinstall helpers: %w", err)
	}

	// Reinstall competing caller-bin artifacts from share (kept intact).
	if err := copyDir(p.ShareCallerBin(), p.CallerBin(), 0o755); err != nil {
		return fmt.Errorf("reinstall caller-bin: %w", err)
	}

	// Reinstall caller-python sitecustomize from share.
	if err := copyDir(p.ShareCallerPython(), p.CallerPython(), 0o644); err != nil {
		return fmt.Errorf("reinstall caller-python: %w", err)
	}

	// Install the gen1 signed manifest from share.
	store := manifest.NewStore(p)
	if _, err := store.Install(p.ShareManifest(), p.ShareSignature()); err != nil {
		return fmt.Errorf("install gen1 manifest: %w", err)
	}

	// Write empty journal / decisions / effects.
	for _, f := range []string{p.Journal(), p.Decisions(), p.Effects()} {
		if err := fsutil.WriteFileSync(f, []byte{}, 0o644); err != nil {
			return err
		}
	}

	// Initialize the event sequence.
	if err := journal.NewStore(p).InitState(); err != nil {
		return err
	}
	return nil
}

// ---- dispatch ------------------------------------------------------------

func cmdDispatch(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("dispatch", flag.ContinueOnError)
	requestPath := fs.String("request", "", "absolute path to request JSON")
	via := fs.String("via", "", "launch surface: direct|job")
	callerEnv := fs.String("caller-env", "", "optional caller env conf")
	trace := fs.String("trace", "", "optional trace output path")
	crashAfter := fs.String("crash-after", "", "optional crash injection: prepared|effect")
	if err := fs.Parse(args); err != nil {
		return err
	}
	surface, err := parseSurface(*via)
	if err != nil {
		return err
	}
	if *requestPath == "" {
		return fmt.Errorf("--request is required")
	}
	if err := applyCallerEnv(*callerEnv); err != nil {
		return err
	}

	data, err := os.ReadFile(*requestPath)
	if err != nil {
		return err
	}
	req, err := canonical.ParseRequest(data)
	if err != nil {
		return err
	}

	d := dispatch.New(p)
	d.SetTrace(*trace)
	rec, err := d.Dispatch(req, surface, *crashAfter)
	if err != nil {
		return err
	}
	return printJSON(rec)
}

// ---- dispatch-batch ------------------------------------------------------

func cmdDispatchBatch(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("dispatch-batch", flag.ContinueOnError)
	fixture := fs.String("fixture", "", "absolute path to JSONL request fixture")
	via := fs.String("via", "", "launch surface: direct|job")
	callerEnv := fs.String("caller-env", "", "optional caller env conf")
	trace := fs.String("trace", "", "optional trace output path")
	if err := fs.Parse(args); err != nil {
		return err
	}
	surface, err := parseSurface(*via)
	if err != nil {
		return err
	}
	if *fixture == "" {
		return fmt.Errorf("--fixture is required")
	}
	if err := applyCallerEnv(*callerEnv); err != nil {
		return err
	}

	f, err := os.Open(*fixture)
	if err != nil {
		return err
	}
	defer f.Close()

	d := dispatch.New(p)
	d.SetTrace(*trace)

	sc := bufio.NewScanner(f)
	sc.Buffer(make([]byte, 0, 1024*1024), 8*1024*1024)
	out := os.Stdout
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" {
			continue
		}
		req, err := canonical.ParseRequest([]byte(line))
		if err != nil {
			return err
		}
		rec, err := d.Dispatch(req, surface, dispatch.CrashNone)
		if err != nil {
			return err
		}
		b, err := json.Marshal(rec)
		if err != nil {
			return err
		}
		fmt.Fprintln(out, string(b))
	}
	return sc.Err()
}

// ---- manifest-install ----------------------------------------------------

func cmdManifestInstall(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("manifest-install", flag.ContinueOnError)
	manifestPath := fs.String("manifest", "", "absolute path to candidate manifest")
	sigPath := fs.String("signature", "", "absolute path to candidate signature")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *manifestPath == "" || *sigPath == "" {
		return fmt.Errorf("--manifest and --signature are required")
	}
	store := manifest.NewStore(p)
	loaded, err := store.Install(*manifestPath, *sigPath)
	if err != nil {
		return err
	}
	return printJSON(map[string]any{
		"installed":           true,
		"scenario":            loaded.Manifest.Scenario,
		"manifest_generation": loaded.Manifest.Generation,
		"manifest_digest":     loaded.Digest,
	})
}

// ---- recover -------------------------------------------------------------

func cmdRecover(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("recover", flag.ContinueOnError)
	trace := fs.String("trace", "", "optional trace output path")
	if err := fs.Parse(args); err != nil {
		return err
	}
	r := recovery.New(p)
	r.SetTrace(*trace)
	sum, err := r.Run()
	if err != nil {
		return err
	}
	return printJSON(sum)
}

// ---- resolved-helpers ----------------------------------------------------

type helperProbe struct {
	HelperName     string `json:"helper_name"`
	HelperPath     string `json:"helper_path"`
	HelperDigest   string `json:"helper_digest"`
	ManifestDigest string `json:"manifest_digest"`
	HelperTrusted  bool   `json:"helper_trusted"`
}

func cmdResolvedHelpers(p model.Paths, args []string) error {
	if len(args) == 0 || args[0] != "dump" {
		return fmt.Errorf("usage: resolved-helpers dump --json [--caller-env ABS]")
	}
	fs := flag.NewFlagSet("resolved-helpers dump", flag.ContinueOnError)
	asJSON := fs.Bool("json", false, "emit JSON")
	callerEnv := fs.String("caller-env", "", "optional caller env conf")
	if err := fs.Parse(args[1:]); err != nil {
		return err
	}
	if err := applyCallerEnv(*callerEnv); err != nil {
		return err
	}

	loaded, err := manifest.NewStore(p).LoadCurrent()
	if err != nil {
		return err
	}
	names := make([]string, 0, len(loaded.Manifest.Helpers))
	for name := range loaded.Manifest.Helpers {
		names = append(names, name)
	}
	sortStrings(names)

	probes := make([]helperProbe, 0, len(names))
	for _, name := range names {
		res := helper.Resolve(p, loaded.Manifest, name)
		probes = append(probes, helperProbe{
			HelperName:     name,
			HelperPath:     res.Path,
			HelperDigest:   res.Digest,
			ManifestDigest: res.Entry.SHA256,
			HelperTrusted:  res.Trusted,
		})
	}

	payload := map[string]any{
		"scenario":            loaded.Manifest.Scenario,
		"manifest_generation": loaded.Manifest.Generation,
		"manifest_digest":     loaded.Digest,
		"probes":              probes,
	}
	if *asJSON {
		return printJSON(payload)
	}
	return printJSON(payload)
}

// ---- exports -------------------------------------------------------------

func cmdJournalExport(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("journal-export", flag.ContinueOnError)
	_ = fs.Bool("json", false, "emit JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	events, err := journal.NewStore(p).LoadAll()
	if err != nil {
		return err
	}
	if events == nil {
		events = []journal.Event{}
	}
	return printJSON(events)
}

func cmdDecisionsExport(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("decisions-export", flag.ContinueOnError)
	_ = fs.Bool("json", false, "emit JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	decisions, err := ledger.NewDecisionStore(p).LoadAll()
	if err != nil {
		return err
	}
	if decisions == nil {
		decisions = []ledger.Decision{}
	}
	return printJSON(decisions)
}

func cmdEffectsExport(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("effects-export", flag.ContinueOnError)
	_ = fs.Bool("json", false, "emit JSON")
	if err := fs.Parse(args); err != nil {
		return err
	}
	effects, err := ledger.NewEffectStore(p).LoadAll()
	if err != nil {
		return err
	}
	if effects == nil {
		effects = []ledger.Effect{}
	}
	return printJSON(effects)
}

// ---- reconcile -----------------------------------------------------------

func cmdReconcile(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("reconcile", flag.ContinueOnError)
	trace := fs.String("trace", "", "trace output path")
	output := fs.String("output", "", "report output path")
	if err := fs.Parse(args); err != nil {
		return err
	}
	if *output == "" {
		return fmt.Errorf("--output is required")
	}
	rep, err := reconcile.New(p).Run(*trace, *output)
	if err != nil {
		return err
	}
	return printJSON(rep)
}

// ---- selftest ------------------------------------------------------------

func cmdSelftest(p model.Paths, args []string) error {
	fs := flag.NewFlagSet("selftest", flag.ContinueOnError)
	mode := fs.String("mode", "", "baseline|security")
	if err := fs.Parse(args); err != nil {
		return err
	}
	switch *mode {
	case "baseline":
		return runSelftest(p, false)
	case "security":
		return runSelftest(p, true)
	default:
		return fmt.Errorf("selftest --mode must be baseline or security")
	}
}

// runSelftest saves the live var/privhelper and reports trees, runs an isolated
// reset+scenario, then restores the originals so the main ledgers are never
// corrupted.
func runSelftest(p model.Paths, security bool) (retErr error) {
	backup, err := os.MkdirTemp("", "privhelper-selftest-*")
	if err != nil {
		return err
	}
	varBak := filepath.Join(backup, "var")
	repBak := filepath.Join(backup, "reports")

	savedVar := moveIfExists(p.VarDir(), varBak)
	savedRep := moveIfExists(p.Reports(), repBak)

	restore := func() {
		_ = fsutil.RemoveAll(p.VarDir())
		_ = fsutil.RemoveAll(p.Reports())
		if savedVar {
			_ = os.Rename(varBak, p.VarDir())
		}
		if savedRep {
			_ = os.Rename(repBak, p.Reports())
		}
		_ = fsutil.RemoveAll(backup)
	}
	defer restore()

	if err := doReset(p); err != nil {
		return fmt.Errorf("selftest reset: %w", err)
	}

	if !security {
		// Baseline: a normal owner seal must be allowed.
		if err := expectAllow(p, model.Request{
			RequestID: "selftest-baseline-1",
			Principal: "ops.owner",
			Action:    "seal_unit",
			Unit:      "selftest-unit",
		}); err != nil {
			return err
		}
		fmt.Println("SELFTEST_OK")
		return nil
	}

	// Security mode contaminates the caller environment before exercising the
	// dispatcher. Resolution must ignore all of these.
	contaminate()

	// 1. Contaminated helper lookup stays trusted and rooted under libexec.
	loaded, err := manifest.NewStore(p).LoadCurrent()
	if err != nil {
		return fmt.Errorf("selftest load manifest: %w", err)
	}
	for name := range loaded.Manifest.Helpers {
		res := helper.Resolve(p, loaded.Manifest, name)
		if !res.Trusted {
			return fmt.Errorf("selftest: helper %q not trusted under contamination", name)
		}
		if filepath.Dir(res.Path) != filepath.Clean(p.Libexec()) {
			return fmt.Errorf("selftest: helper %q resolved outside libexec: %s", name, res.Path)
		}
	}

	// 2. Denied principal must be denied with no effect.
	if err := expectDeny(p, model.Request{
		RequestID: "selftest-denied-1",
		Principal: "ops.guest",
		Action:    "export_bundle",
		Unit:      "selftest-unit",
	}); err != nil {
		return err
	}

	// 3. Exact retry idempotency: an allowed owner seal replayed with an
	// identical body produces no second effect.
	allowReq := model.Request{
		RequestID: "selftest-retry-1",
		Principal: "ops.owner",
		Action:    "seal_unit",
		Unit:      "selftest-unit",
	}
	if err := expectAllow(p, allowReq); err != nil {
		return err
	}
	beforeEffects, err := ledger.NewEffectStore(p).FindByRequestID(allowReq.RequestID)
	if err != nil {
		return err
	}
	if err := expectAllow(p, allowReq); err != nil {
		return err
	}
	afterEffects, err := ledger.NewEffectStore(p).FindByRequestID(allowReq.RequestID)
	if err != nil {
		return err
	}
	if len(afterEffects) != len(beforeEffects) {
		return fmt.Errorf("selftest: exact retry produced a duplicate effect")
	}

	// 4. Reconcile must find sound authority.
	tracePath := filepath.Join(p.Reports(), "selftest-reconcile-trace.jsonl")
	outPath := filepath.Join(p.Reports(), "selftest-authority-report.json")
	rep, err := reconcile.New(p).Run(tracePath, outPath)
	if err != nil {
		return err
	}
	if !rep.AuthoritySound {
		return fmt.Errorf("selftest: reconcile reported unsound authority: %v", rep.Violations)
	}

	fmt.Println("SECURITY_SELFTEST_OK")
	return nil
}

func expectAllow(p model.Paths, req model.Request) error {
	rec, err := dispatch.New(p).Dispatch(req, model.LaunchDirect, dispatch.CrashNone)
	if err != nil {
		return err
	}
	if rec.Decision != model.DecisionAllow {
		return fmt.Errorf("selftest: expected allow for %s/%s, got %s (%s)", req.Principal, req.Action, rec.Decision, rec.Reason)
	}
	return nil
}

func expectDeny(p model.Paths, req model.Request) error {
	rec, err := dispatch.New(p).Dispatch(req, model.LaunchJob, dispatch.CrashNone)
	if err != nil {
		return err
	}
	if rec.Decision != model.DecisionDeny || rec.Outcome != model.OutcomeNone {
		return fmt.Errorf("selftest: expected deny/none for %s/%s, got %s/%s", req.Principal, req.Action, rec.Decision, rec.Outcome)
	}
	return nil
}

func contaminate() {
	os.Setenv("HELPER_PATH", "/app/var/caller-bin")
	os.Setenv("PATH", "/app/var/caller-bin:/usr/local/bin:/usr/bin:/bin")
	os.Setenv("PYTHONPATH", "/app/var/caller-python")
}

// ---- shared helpers ------------------------------------------------------

func parseSurface(via string) (string, error) {
	switch via {
	case model.LaunchDirect, model.LaunchJob:
		return via, nil
	default:
		return "", fmt.Errorf("--via must be direct or job")
	}
}

// applyCallerEnv reads a KEY=VALUE conf file and sets those variables into the
// process environment. This deliberately lets contaminated caller inputs into
// the process so probes are realistic; helper execution still uses an
// allowlisted environment and never trusts these values.
func applyCallerEnv(path string) error {
	if path == "" {
		return nil
	}
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()

	sc := bufio.NewScanner(f)
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		eq := strings.IndexByte(line, '=')
		if eq < 0 {
			continue
		}
		key := strings.TrimSpace(line[:eq])
		val := strings.TrimSpace(line[eq+1:])
		if key == "" {
			continue
		}
		if err := os.Setenv(key, val); err != nil {
			return err
		}
	}
	return sc.Err()
}

func printJSON(v any) error {
	b, err := json.MarshalIndent(v, "", "  ")
	if err != nil {
		return err
	}
	fmt.Println(string(b))
	return nil
}

func moveIfExists(src, dst string) bool {
	if _, err := os.Stat(src); err != nil {
		return false
	}
	if err := fsutil.EnsureDir(filepath.Dir(dst)); err != nil {
		return false
	}
	if err := os.Rename(src, dst); err != nil {
		return false
	}
	return true
}

func copyGlob(srcDir, pattern, dstDir string, perm os.FileMode) error {
	matches, err := filepath.Glob(filepath.Join(srcDir, pattern))
	if err != nil {
		return err
	}
	if err := fsutil.EnsureDir(dstDir); err != nil {
		return err
	}
	for _, m := range matches {
		if err := copyFile(m, filepath.Join(dstDir, filepath.Base(m)), perm); err != nil {
			return err
		}
	}
	return nil
}

func copyDir(srcDir, dstDir string, perm os.FileMode) error {
	entries, err := os.ReadDir(srcDir)
	if err != nil {
		return err
	}
	if err := fsutil.EnsureDir(dstDir); err != nil {
		return err
	}
	for _, e := range entries {
		if e.IsDir() {
			if err := copyDir(filepath.Join(srcDir, e.Name()), filepath.Join(dstDir, e.Name()), perm); err != nil {
				return err
			}
			continue
		}
		if err := copyFile(filepath.Join(srcDir, e.Name()), filepath.Join(dstDir, e.Name()), perm); err != nil {
			return err
		}
	}
	return nil
}

func copyFile(src, dst string, perm os.FileMode) error {
	in, err := os.Open(src)
	if err != nil {
		return err
	}
	defer in.Close()
	if err := fsutil.EnsureDir(filepath.Dir(dst)); err != nil {
		return err
	}
	out, err := os.OpenFile(dst, os.O_CREATE|os.O_WRONLY|os.O_TRUNC, perm)
	if err != nil {
		return err
	}
	if _, err := io.Copy(out, in); err != nil {
		out.Close()
		return err
	}
	if err := out.Sync(); err != nil {
		out.Close()
		return err
	}
	return out.Close()
}

func sortStrings(s []string) {
	for i := 1; i < len(s); i++ {
		for j := i; j > 0 && s[j-1] > s[j]; j-- {
			s[j-1], s[j] = s[j], s[j-1]
		}
	}
}
