package main

import (
	"bytes"
	"crypto/hmac"
	"crypto/sha256"
	"encoding/hex"
	"encoding/json"
	"fmt"
	"os"
	"path/filepath"
	"sort"
	"strconv"
	"strings"
)

type Share struct {
	Holder    string
	Role      string
	Epoch     string
	X         int
	Y         int
	State     string
	NotBefore int
	NotAfter  int
	MAC       string
}

type LineageEdge struct {
	Parent           string
	Child            string
	Offset           int
	ContinuityRoles  []string
	ContinuityQuorum int
	HandoffSeals     []string
}

type Case struct {
	CaseID          string
	Prime           int
	Threshold       int
	MaxOutliers     int
	AuditTime       int
	AuthKeyHex      string
	RequiredRoles   []string
	RoleLimits      map[string]int
	Commitments     map[string]string
	Lineage         []LineageEdge
	MinLineageDepth int
	Shares          []Share
}

type Rejection struct {
	Epoch  string `json:"epoch"`
	Holder string `json:"holder"`
	Reason string `json:"reason"`
}

type Report struct {
	CaseID              string      `json:"case_id"`
	Status              string      `json:"status"`
	Reason              *string     `json:"reason"`
	SelectedEpoch       *string     `json:"selected_epoch"`
	LineageEpochs       []string    `json:"lineage_epochs"`
	ContinuityHolders   []string    `json:"continuity_holders"`
	ContinuityChain     [][]string  `json:"continuity_chain"`
	SelectedHolders     []string    `json:"selected_holders"`
	SupportHolders      []string    `json:"support_holders"`
	OutlierHolders      []string    `json:"outlier_holders"`
	SupportShareCount   int         `json:"support_share_count"`
	SecretMod           *string     `json:"secret_mod"`
	ValidShareCount     int         `json:"valid_share_count"`
	EvaluatedModelCount int         `json:"evaluated_model_count"`
	ModelFrontierDigest string      `json:"model_frontier_digest"`
	Rejected            []Rejection `json:"rejected"`
	EvidenceDigest      string      `json:"evidence_digest"`
}

type Model struct {
	Epoch             string
	Witness           []Share
	Support           []Share
	Outliers          []Share
	Secret            int
	PolicyOK          bool
	CommitmentOK      bool
	LineageDepth      int
	LineageEpochs     []string
	ContinuityHolders []string
	ContinuityChain   [][]string
}

type LineageState struct {
	Depth  int
	Epochs []string
	Chain  [][]string
	Used   map[string]bool
}

func main() {
	if len(os.Args) != 3 {
		invalid()
	}
	data, err := os.ReadFile(os.Args[1])
	if err != nil {
		invalid()
	}
	c, err := parseCase(data)
	if err != nil {
		invalid()
	}
	report := solve(c)
	out, err := json.Marshal(report)
	if err != nil {
		invalid()
	}
	out = append(out, '\n')
	if err := atomicWrite(os.Args[2], out); err != nil {
		invalid()
	}
}

func invalid() {
	fmt.Fprintln(os.Stderr, "vaultquorum: invalid input")
	os.Exit(2)
}

func atomicWrite(path string, data []byte) error {
	dir := filepath.Dir(path)
	file, err := os.CreateTemp(dir, ".vaultquorum-*")
	if err != nil {
		return err
	}
	tmp := file.Name()
	defer os.Remove(tmp)
	if _, err := file.Write(data); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Chmod(0644); err != nil {
		_ = file.Close()
		return err
	}
	if err := file.Close(); err != nil {
		return err
	}
	return os.Rename(tmp, path)
}

func parseCase(data []byte) (Case, error) {
	var raw map[string]json.RawMessage
	if err := json.Unmarshal(data, &raw); err != nil || raw == nil {
		return Case{}, fmt.Errorf("bad object")
	}
	required := []string{
		"case_id", "prime", "threshold", "max_outliers", "audit_time", "auth_key_hex",
		"required_roles", "role_limits", "commitments", "lineage", "min_lineage_depth", "shares",
	}
	if len(raw) != len(required) {
		return Case{}, fmt.Errorf("wrong top-level fields")
	}
	for _, key := range required {
		if _, ok := raw[key]; !ok {
			return Case{}, fmt.Errorf("missing %s", key)
		}
	}

	var c Case
	var err error
	if c.CaseID, err = exactString(raw["case_id"]); err != nil || c.CaseID == "" {
		return Case{}, fmt.Errorf("bad case_id")
	}
	if c.Prime, err = exactInt(raw["prime"]); err != nil || c.Prime < 3 || c.Prime > 65537 || !isPrime(c.Prime) {
		return Case{}, fmt.Errorf("bad prime")
	}
	if c.Threshold, err = exactInt(raw["threshold"]); err != nil || c.Threshold < 1 || c.Threshold > 8 {
		return Case{}, fmt.Errorf("bad threshold")
	}
	if c.MaxOutliers, err = exactInt(raw["max_outliers"]); err != nil || c.MaxOutliers < 0 {
		return Case{}, fmt.Errorf("bad max_outliers")
	}
	if c.AuditTime, err = exactInt(raw["audit_time"]); err != nil {
		return Case{}, fmt.Errorf("bad audit_time")
	}
	if c.AuthKeyHex, err = exactString(raw["auth_key_hex"]); err != nil || c.AuthKeyHex == "" {
		return Case{}, fmt.Errorf("bad auth key")
	}
	if _, err := hex.DecodeString(c.AuthKeyHex); err != nil {
		return Case{}, err
	}
	if c.RequiredRoles, err = exactStringArray(raw["required_roles"]); err != nil {
		return Case{}, err
	}
	seenRoles := map[string]bool{}
	for _, role := range c.RequiredRoles {
		if role == "" || seenRoles[role] {
			return Case{}, fmt.Errorf("bad required role")
		}
		seenRoles[role] = true
	}
	if c.RoleLimits, err = exactStringIntMap(raw["role_limits"]); err != nil {
		return Case{}, err
	}
	for role, cap := range c.RoleLimits {
		if role == "" || cap < 0 {
			return Case{}, fmt.Errorf("bad role limit")
		}
	}
	if c.Commitments, err = exactStringMap(raw["commitments"]); err != nil || len(c.Commitments) == 0 || len(c.Commitments) > 12 {
		return Case{}, fmt.Errorf("bad commitments")
	}
	for epoch, commitment := range c.Commitments {
		if epoch == "" || !validPrefixedDigest(commitment) {
			return Case{}, fmt.Errorf("bad commitment")
		}
	}
	if c.Lineage, err = parseLineage(raw["lineage"], c.Prime, c.Commitments); err != nil {
		return Case{}, err
	}
	if c.MinLineageDepth, err = exactInt(raw["min_lineage_depth"]); err != nil || c.MinLineageDepth < 1 || c.MinLineageDepth > len(c.Commitments) {
		return Case{}, fmt.Errorf("bad min lineage depth")
	}
	if c.Shares, err = parseShares(raw["shares"], c.Prime, c.Commitments); err != nil {
		return Case{}, err
	}
	return c, nil
}

func exactString(raw json.RawMessage) (string, error) {
	var value string
	if err := json.Unmarshal(raw, &value); err != nil {
		return "", err
	}
	return value, nil
}

func exactInt(raw json.RawMessage) (int, error) {
	trimmed := strings.TrimSpace(string(raw))
	if trimmed == "" || trimmed == "-" || strings.ContainsAny(trimmed, ".eE+\"") {
		return 0, fmt.Errorf("not an integer token")
	}
	if trimmed == "true" || trimmed == "false" || trimmed == "null" || trimmed[0] == '[' || trimmed[0] == '{' {
		return 0, fmt.Errorf("not an integer token")
	}
	value, err := strconv.ParseInt(trimmed, 10, 64)
	if err != nil {
		return 0, err
	}
	converted := int(value)
	if int64(converted) != value {
		return 0, fmt.Errorf("integer overflow")
	}
	return converted, nil
}

func exactStringArray(raw json.RawMessage) ([]string, error) {
	var values []json.RawMessage
	if err := json.Unmarshal(raw, &values); err != nil || values == nil {
		return nil, fmt.Errorf("not a string array")
	}
	result := make([]string, len(values))
	for i, item := range values {
		value, err := exactString(item)
		if err != nil {
			return nil, err
		}
		result[i] = value
	}
	return result, nil
}

func exactStringIntMap(raw json.RawMessage) (map[string]int, error) {
	var values map[string]json.RawMessage
	if err := json.Unmarshal(raw, &values); err != nil || values == nil {
		return nil, fmt.Errorf("not an integer map")
	}
	result := make(map[string]int, len(values))
	for key, item := range values {
		value, err := exactInt(item)
		if err != nil {
			return nil, err
		}
		result[key] = value
	}
	return result, nil
}

func exactStringMap(raw json.RawMessage) (map[string]string, error) {
	var values map[string]json.RawMessage
	if err := json.Unmarshal(raw, &values); err != nil || values == nil {
		return nil, fmt.Errorf("not a string map")
	}
	result := make(map[string]string, len(values))
	for key, item := range values {
		value, err := exactString(item)
		if err != nil {
			return nil, err
		}
		result[key] = value
	}
	return result, nil
}

func parseLineage(raw json.RawMessage, prime int, commitments map[string]string) ([]LineageEdge, error) {
	var encoded []json.RawMessage
	maxEdges := len(commitments) * (len(commitments) - 1) / 2
	if err := json.Unmarshal(raw, &encoded); err != nil || encoded == nil || len(encoded) > maxEdges {
		return nil, fmt.Errorf("bad lineage")
	}
	edges := make([]LineageEdge, 0, len(encoded))
	seenPairs := map[string]bool{}
	adjacency := map[string][]string{}
	for _, itemRaw := range encoded {
		var item map[string]json.RawMessage
		if err := json.Unmarshal(itemRaw, &item); err != nil || item == nil || len(item) != 6 {
			return nil, fmt.Errorf("bad lineage edge")
		}
		for _, key := range []string{"parent", "child", "offset", "continuity_roles", "continuity_quorum", "handoff_seals"} {
			if _, ok := item[key]; !ok {
				return nil, fmt.Errorf("missing lineage field")
			}
		}
		parent, err := exactString(item["parent"])
		if err != nil || parent == "" {
			return nil, fmt.Errorf("bad lineage parent")
		}
		child, err := exactString(item["child"])
		if err != nil || child == "" || child == parent {
			return nil, fmt.Errorf("bad lineage child")
		}
		if _, ok := commitments[parent]; !ok {
			return nil, fmt.Errorf("unknown lineage parent")
		}
		if _, ok := commitments[child]; !ok {
			return nil, fmt.Errorf("unknown lineage child")
		}
		pairKey := parent + "\x00" + child
		if seenPairs[pairKey] {
			return nil, fmt.Errorf("duplicate lineage edge")
		}
		seenPairs[pairKey] = true
		offset, err := exactInt(item["offset"])
		if err != nil || offset < 0 || offset >= prime {
			return nil, fmt.Errorf("bad lineage offset")
		}
		continuityRoles, err := exactStringArray(item["continuity_roles"])
		if err != nil {
			return nil, fmt.Errorf("bad continuity roles")
		}
		seenRoles := map[string]bool{}
		for _, role := range continuityRoles {
			if role == "" || seenRoles[role] {
				return nil, fmt.Errorf("bad continuity role")
			}
			seenRoles[role] = true
		}
		continuityQuorum, err := exactInt(item["continuity_quorum"])
		if err != nil || continuityQuorum < 1 || continuityQuorum > 18 || len(continuityRoles) > continuityQuorum {
			return nil, fmt.Errorf("bad continuity quorum")
		}
		handoffSeals, err := exactStringArray(item["handoff_seals"])
		if err != nil || len(handoffSeals) < 1 || len(handoffSeals) > 18 {
			return nil, fmt.Errorf("bad lineage seals")
		}
		seenSeals := map[string]bool{}
		for _, seal := range handoffSeals {
			if !validPrefixedDigest(seal) || seenSeals[seal] {
				return nil, fmt.Errorf("bad lineage seal")
			}
			seenSeals[seal] = true
		}
		edges = append(edges, LineageEdge{
			Parent: parent, Child: child, Offset: offset,
			ContinuityRoles: continuityRoles, ContinuityQuorum: continuityQuorum, HandoffSeals: handoffSeals,
		})
		adjacency[parent] = append(adjacency[parent], child)
	}

	visiting := map[string]int{}
	var visit func(string) bool
	visit = func(epoch string) bool {
		if visiting[epoch] == 1 {
			return false
		}
		if visiting[epoch] == 2 {
			return true
		}
		visiting[epoch] = 1
		for _, child := range adjacency[epoch] {
			if !visit(child) {
				return false
			}
		}
		visiting[epoch] = 2
		return true
	}
	for epoch := range commitments {
		if !visit(epoch) {
			return nil, fmt.Errorf("lineage cycle")
		}
	}
	return edges, nil
}

func parseShares(raw json.RawMessage, prime int, commitments map[string]string) ([]Share, error) {
	var shareRaws []json.RawMessage
	if err := json.Unmarshal(raw, &shareRaws); err != nil || len(shareRaws) < 1 || len(shareRaws) > 18 {
		return nil, fmt.Errorf("bad shares")
	}
	shareKeys := []string{"holder", "role", "epoch", "x", "y", "state", "not_before", "not_after", "mac"}
	shares := make([]Share, 0, len(shareRaws))
	seenEpochHolder := map[string]bool{}
	for _, encoded := range shareRaws {
		var item map[string]json.RawMessage
		if err := json.Unmarshal(encoded, &item); err != nil || item == nil || len(item) != len(shareKeys) {
			return nil, fmt.Errorf("wrong share fields")
		}
		for _, key := range shareKeys {
			if _, ok := item[key]; !ok {
				return nil, fmt.Errorf("missing share field")
			}
		}
		var share Share
		var err error
		if share.Holder, err = exactString(item["holder"]); err != nil || share.Holder == "" {
			return nil, fmt.Errorf("bad holder")
		}
		if share.Role, err = exactString(item["role"]); err != nil || share.Role == "" {
			return nil, fmt.Errorf("bad role")
		}
		if share.Epoch, err = exactString(item["epoch"]); err != nil || share.Epoch == "" {
			return nil, fmt.Errorf("bad epoch")
		}
		if _, ok := commitments[share.Epoch]; !ok {
			return nil, fmt.Errorf("unknown epoch")
		}
		if share.X, err = exactInt(item["x"]); err != nil || share.X <= 0 || share.X >= prime {
			return nil, fmt.Errorf("bad x")
		}
		if share.Y, err = exactInt(item["y"]); err != nil || share.Y < 0 || share.Y >= prime {
			return nil, fmt.Errorf("bad y")
		}
		if share.State, err = exactString(item["state"]); err != nil {
			return nil, fmt.Errorf("bad state")
		}
		if share.NotBefore, err = exactInt(item["not_before"]); err != nil {
			return nil, fmt.Errorf("bad not_before")
		}
		if share.NotAfter, err = exactInt(item["not_after"]); err != nil || share.NotAfter < share.NotBefore {
			return nil, fmt.Errorf("bad not_after")
		}
		if share.MAC, err = exactString(item["mac"]); err != nil || !isLowerHex(share.MAC, 64) {
			return nil, fmt.Errorf("bad mac")
		}
		holderKey := share.Epoch + "\x00" + share.Holder
		if seenEpochHolder[holderKey] {
			return nil, fmt.Errorf("duplicate epoch holder")
		}
		seenEpochHolder[holderKey] = true
		shares = append(shares, share)
	}
	return shares, nil
}

func isLowerHex(value string, length int) bool {
	if len(value) != length {
		return false
	}
	for _, ch := range value {
		if !((ch >= '0' && ch <= '9') || (ch >= 'a' && ch <= 'f')) {
			return false
		}
	}
	return true
}

func validPrefixedDigest(value string) bool {
	return strings.HasPrefix(value, "sha256:") && isLowerHex(strings.TrimPrefix(value, "sha256:"), 64)
}

func isPrime(n int) bool {
	if n < 2 {
		return false
	}
	for divisor := 2; divisor*divisor <= n; divisor++ {
		if n%divisor == 0 {
			return false
		}
	}
	return true
}

func solve(c Case) Report {
	key, _ := hex.DecodeString(c.AuthKeyHex)
	initial := make([]Share, 0, len(c.Shares))
	rejected := make([]Rejection, 0)
	for _, share := range c.Shares {
		reason := ""
		switch {
		case !validMAC(c, share, key):
			reason = "bad_mac"
		case share.State != "active":
			reason = "inactive"
		case c.AuditTime < share.NotBefore || c.AuditTime > share.NotAfter:
			reason = "outside_window"
		}
		if reason == "" {
			initial = append(initial, share)
		} else {
			rejected = append(rejected, Rejection{Epoch: share.Epoch, Holder: share.Holder, Reason: reason})
		}
	}

	coordinateCounts := map[string]int{}
	for _, share := range initial {
		coordinateCounts[coordinateKey(share)]++
	}
	eligible := make([]Share, 0, len(initial))
	for _, share := range initial {
		if coordinateCounts[coordinateKey(share)] > 1 {
			rejected = append(rejected, Rejection{Epoch: share.Epoch, Holder: share.Holder, Reason: "duplicate_x"})
		} else {
			eligible = append(eligible, share)
		}
	}
	sort.Slice(rejected, func(i, j int) bool {
		if rejected[i].Epoch != rejected[j].Epoch {
			return rejected[i].Epoch < rejected[j].Epoch
		}
		if rejected[i].Holder != rejected[j].Holder {
			return rejected[i].Holder < rejected[j].Holder
		}
		return rejected[i].Reason < rejected[j].Reason
	})

	best, blockReason, models := chooseRobustCandidate(c, eligible)
	report := Report{
		CaseID:              c.CaseID,
		LineageEpochs:       []string{},
		ContinuityHolders:   []string{},
		ContinuityChain:     [][]string{},
		SelectedHolders:     []string{},
		SupportHolders:      []string{},
		OutlierHolders:      []string{},
		ValidShareCount:     len(eligible),
		EvaluatedModelCount: len(models),
		ModelFrontierDigest: modelFrontierDigest(models),
		Rejected:            rejected,
	}
	if best == nil {
		report.Status = "blocked"
		report.Reason = &blockReason
		report.SelectedEpoch = nil
		report.SecretMod = nil
	} else {
		report.Status = "recovered"
		report.Reason = nil
		epoch := best.Epoch
		report.SelectedEpoch = &epoch
		report.LineageEpochs = append([]string(nil), best.LineageEpochs...)
		report.ContinuityHolders = append([]string{}, best.ContinuityHolders...)
		report.ContinuityChain = copyChain(best.ContinuityChain)
		report.SelectedHolders = holderList(best.Witness)
		report.SupportHolders = holderList(best.Support)
		report.OutlierHolders = holderList(best.Outliers)
		report.SupportShareCount = len(best.Support)
		secret := strconv.Itoa(best.Secret)
		report.SecretMod = &secret
	}
	report.EvidenceDigest = evidenceDigest(report)
	return report
}

func coordinateKey(share Share) string {
	return share.Epoch + "\x00" + strconv.Itoa(share.X)
}

func validMAC(c Case, share Share, key []byte) bool {
	message := fmt.Sprintf("%s\n%s\n%s\n%s\n%d\n%d\n%d\n%d\n%s\n", c.CaseID, share.Holder, share.Role, share.Epoch, share.X, share.Y, share.NotBefore, share.NotAfter, share.State)
	mac := hmac.New(sha256.New, key)
	_, _ = mac.Write([]byte(message))
	got, err := hex.DecodeString(share.MAC)
	if err != nil {
		return false
	}
	return hmac.Equal(got, mac.Sum(nil))
}

func chooseRobustCandidate(c Case, eligible []Share) (*Model, string, []Model) {
	byEpoch := map[string][]Share{}
	for _, share := range eligible {
		byEpoch[share.Epoch] = append(byEpoch[share.Epoch], share)
	}
	epochs := make([]string, 0, len(byEpoch))
	for epoch := range byEpoch {
		epochs = append(epochs, epoch)
	}
	sort.Strings(epochs)

	hasEnough := false
	hasConsensus := false
	hasPolicy := false
	models := make([]Model, 0)
	for _, epoch := range epochs {
		shares := append([]Share(nil), byEpoch[epoch]...)
		sortShares(shares)
		if len(shares) < c.Threshold {
			continue
		}
		hasEnough = true
		seenModels := map[string]bool{}
		visitCombinations(shares, c.Threshold, func(seed []Share) {
			modelID := polynomialKey(seed, c.Threshold, c.Prime)
			if seenModels[modelID] {
				return
			}
			seenModels[modelID] = true
			support := make([]Share, 0, len(shares))
			outliers := make([]Share, 0)
			for _, share := range shares {
				if evaluateAt(seed, share.X, c.Prime) == share.Y {
					support = append(support, share)
				} else {
					outliers = append(outliers, share)
				}
			}
			if len(outliers) > c.MaxOutliers {
				return
			}
			hasConsensus = true
			witness := bestPolicyWitness(support, c.Threshold, c.RequiredRoles, c.RoleLimits)
			policyOK := witness != nil
			if policyOK {
				hasPolicy = true
			}
			secret := evaluateAt(seed, 0, c.Prime)
			commitmentOK := secretCommitment(c.CaseID, epoch, secret) == c.Commitments[epoch]
			model := Model{
				Epoch:        epoch,
				Witness:      witness,
				Support:      append([]Share(nil), support...),
				Outliers:     append([]Share(nil), outliers...),
				Secret:       secret,
				PolicyOK:     policyOK,
				CommitmentOK: commitmentOK,
			}
			models = append(models, model)
		})
	}

	assignLineageStates(c, models)
	hasCommittedPolicy := false
	var best *Model
	for i := range models {
		model := &models[i]
		if model.PolicyOK && model.CommitmentOK {
			hasCommittedPolicy = true
		}
		if model.LineageDepth >= c.MinLineageDepth && (best == nil || candidateLess(model, best)) {
			best = model
		}
	}

	if best != nil {
		copyModel := *best
		copyModel.LineageEpochs = append([]string(nil), best.LineageEpochs...)
		copyModel.ContinuityHolders = append([]string{}, best.ContinuityHolders...)
		copyModel.ContinuityChain = copyChain(best.ContinuityChain)
		return &copyModel, "", models
	}
	if !hasEnough {
		return nil, "not_enough_valid_shares", models
	}
	if !hasConsensus {
		return nil, "consensus_not_reached", models
	}
	if !hasPolicy {
		return nil, "role_requirement_unsatisfied", models
	}
	if !hasCommittedPolicy {
		return nil, "commitment_mismatch", models
	}
	return nil, "lineage_not_reached", models
}

func assignLineageStates(c Case, models []Model) {
	incoming := map[string][]LineageEdge{}
	outgoing := map[string][]string{}
	indegree := map[string]int{}
	modelsByEpoch := map[string][]int{}
	for epoch := range c.Commitments {
		indegree[epoch] = 0
	}
	for _, edge := range c.Lineage {
		incoming[edge.Child] = append(incoming[edge.Child], edge)
		outgoing[edge.Parent] = append(outgoing[edge.Parent], edge.Child)
		indegree[edge.Child]++
	}
	for child := range incoming {
		sort.Slice(incoming[child], func(i, j int) bool {
			if incoming[child][i].Parent != incoming[child][j].Parent {
				return incoming[child][i].Parent < incoming[child][j].Parent
			}
			return incoming[child][i].Child < incoming[child][j].Child
		})
	}
	for i := range models {
		modelsByEpoch[models[i].Epoch] = append(modelsByEpoch[models[i].Epoch], i)
	}

	queue := make([]string, 0)
	for epoch, degree := range indegree {
		if degree == 0 {
			queue = append(queue, epoch)
		}
	}
	sort.Strings(queue)
	topological := make([]string, 0, len(c.Commitments))
	for len(queue) > 0 {
		epoch := queue[0]
		queue = queue[1:]
		topological = append(topological, epoch)
		children := append([]string(nil), outgoing[epoch]...)
		sort.Strings(children)
		for _, child := range children {
			indegree[child]--
			if indegree[child] == 0 {
				queue = append(queue, child)
				sort.Strings(queue)
			}
		}
	}

	states := make([]map[string]LineageState, len(models))
	for i := range states {
		states[i] = map[string]LineageState{}
	}
	for _, epoch := range topological {
		for _, modelIndex := range modelsByEpoch[epoch] {
			model := &models[modelIndex]
			if !model.PolicyOK || !model.CommitmentOK {
				continue
			}
			if len(incoming[epoch]) == 0 {
				state := LineageState{Depth: 1, Epochs: []string{epoch}, Chain: [][]string{}, Used: map[string]bool{}}
				states[modelIndex][usedKey(state.Used)] = state
			}
			for _, edge := range incoming[epoch] {
				for _, parentIndex := range modelsByEpoch[edge.Parent] {
					parent := &models[parentIndex]
					if model.Secret != int(mod(int64(parent.Secret+edge.Offset), int64(c.Prime))) {
						continue
					}
					for _, parentState := range states[parentIndex] {
						for _, holders := range continuityWitnesses(parent.Support, model.Support, edge, parentState.Used) {
							if !containsString(edge.HandoffSeals, transitionSeal(c.CaseID, edge, parent.Secret, model.Secret, holders)) {
								continue
							}
							used := copyUsed(parentState.Used)
							for _, holder := range holders {
								used[holder] = true
							}
							state := LineageState{
								Depth:  parentState.Depth + 1,
								Epochs: append(append([]string(nil), parentState.Epochs...), epoch),
								Chain:  append(copyChain(parentState.Chain), append([]string(nil), holders...)),
								Used:   used,
							}
							key := usedKey(used)
							if current, ok := states[modelIndex][key]; !ok || lineageStateLess(state, current) {
								states[modelIndex][key] = state
							}
						}
					}
				}
			}
			var best *LineageState
			for _, state := range states[modelIndex] {
				copyState := state
				if best == nil || lineageStateLess(copyState, *best) {
					best = &copyState
				}
			}
			if best != nil {
				model.LineageDepth = best.Depth
				model.LineageEpochs = append([]string(nil), best.Epochs...)
				model.ContinuityChain = copyChain(best.Chain)
				if len(best.Chain) > 0 {
					model.ContinuityHolders = append([]string(nil), best.Chain[len(best.Chain)-1]...)
				} else {
					model.ContinuityHolders = []string{}
				}
			}
		}
	}
}

func continuityWitnesses(parentSupport, childSupport []Share, edge LineageEdge, used map[string]bool) [][]string {
	childByHolder := map[string]Share{}
	for _, share := range childSupport {
		childByHolder[share.Holder] = share
	}
	candidates := make([]Share, 0)
	for _, share := range parentSupport {
		child, ok := childByHolder[share.Holder]
		if ok && child.Role == share.Role && !used[share.Holder] {
			candidates = append(candidates, share)
		}
	}
	sortShares(candidates)
	all := make([][]string, 0)
	visitCombinations(candidates, edge.ContinuityQuorum, func(subset []Share) {
		counts := map[string]int{}
		for _, share := range subset {
			counts[share.Role]++
		}
		for _, role := range edge.ContinuityRoles {
			if counts[role] == 0 {
				return
			}
		}
		holders := holderList(subset)
		all = append(all, holders)
	})
	sort.Slice(all, func(i, j int) bool { return compareStrings(all[i], all[j]) < 0 })
	return all
}

func containsString(values []string, wanted string) bool {
	for _, value := range values {
		if value == wanted {
			return true
		}
	}
	return false
}

func copyUsed(source map[string]bool) map[string]bool {
	result := make(map[string]bool, len(source))
	for holder := range source {
		result[holder] = true
	}
	return result
}

func usedKey(used map[string]bool) string {
	holders := make([]string, 0, len(used))
	for holder := range used {
		holders = append(holders, holder)
	}
	sort.Strings(holders)
	encoded, _ := json.Marshal(holders)
	return string(encoded)
}

func copyChain(chain [][]string) [][]string {
	result := make([][]string, len(chain))
	for i, holders := range chain {
		result[i] = append([]string(nil), holders...)
	}
	return result
}

func compareChain(left, right [][]string) int {
	limit := len(left)
	if len(right) < limit {
		limit = len(right)
	}
	for i := 0; i < limit; i++ {
		if order := compareStrings(left[i], right[i]); order != 0 {
			return order
		}
	}
	if len(left) < len(right) {
		return -1
	}
	if len(left) > len(right) {
		return 1
	}
	return 0
}

func lineageStateLess(left, right LineageState) bool {
	if left.Depth != right.Depth {
		return left.Depth > right.Depth
	}
	if order := compareStrings(left.Epochs, right.Epochs); order != 0 {
		return order < 0
	}
	return compareChain(left.Chain, right.Chain) < 0
}

func transitionSeal(caseID string, edge LineageEdge, parentSecret, childSecret int, holders []string) string {
	payload := fmt.Sprintf("%s\n%s\n%s\n%d\n%d\n%d\n%s\n", caseID, edge.Parent, edge.Child, edge.Offset, parentSecret, childSecret, strings.Join(holders, ","))
	sum := sha256.Sum256([]byte(payload))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func lineageEpochPath(epoch string, parentByChild map[string]LineageEdge) []string {
	reversed := []string{epoch}
	current := epoch
	for {
		edge, ok := parentByChild[current]
		if !ok {
			break
		}
		reversed = append(reversed, edge.Parent)
		current = edge.Parent
	}
	path := make([]string, len(reversed))
	for i := range reversed {
		path[len(reversed)-1-i] = reversed[i]
	}
	return path
}

func polynomialKey(seed []Share, threshold, prime int) string {
	parts := make([]string, threshold)
	for x := 0; x < threshold; x++ {
		parts[x] = strconv.Itoa(evaluateAt(seed, x, prime))
	}
	return strings.Join(parts, ",")
}

func bestPolicyWitness(support []Share, threshold int, requiredRoles []string, limits map[string]int) []Share {
	ordered := append([]Share(nil), support...)
	sortShares(ordered)
	var best []Share
	visitCombinations(ordered, threshold, func(subset []Share) {
		if !quorumPolicyOK(subset, requiredRoles, limits) {
			return
		}
		if best == nil || compareStrings(holderList(subset), holderList(best)) < 0 {
			best = append([]Share(nil), subset...)
		}
	})
	return best
}

func visitCombinations(shares []Share, choose int, fn func([]Share)) {
	current := make([]Share, 0, choose)
	var visit func(int)
	visit = func(start int) {
		if len(current) == choose {
			fn(append([]Share(nil), current...))
			return
		}
		need := choose - len(current)
		for i := start; i <= len(shares)-need; i++ {
			current = append(current, shares[i])
			visit(i + 1)
			current = current[:len(current)-1]
		}
	}
	visit(0)
}

func quorumPolicyOK(shares []Share, requiredRoles []string, limits map[string]int) bool {
	counts := map[string]int{}
	for _, share := range shares {
		counts[share.Role]++
		if cap, ok := limits[share.Role]; ok && counts[share.Role] > cap {
			return false
		}
	}
	for _, role := range requiredRoles {
		if counts[role] == 0 {
			return false
		}
	}
	return true
}

func candidateLess(left, right *Model) bool {
	if left.LineageDepth != right.LineageDepth {
		return left.LineageDepth > right.LineageDepth
	}
	if len(left.Support) != len(right.Support) {
		return len(left.Support) > len(right.Support)
	}
	if left.Epoch != right.Epoch {
		return left.Epoch < right.Epoch
	}
	witnessOrder := compareStrings(holderList(left.Witness), holderList(right.Witness))
	if witnessOrder != 0 {
		return witnessOrder < 0
	}
	if pathOrder := compareStrings(left.LineageEpochs, right.LineageEpochs); pathOrder != 0 {
		return pathOrder < 0
	}
	return compareChain(left.ContinuityChain, right.ContinuityChain) < 0
}

func compareStrings(left, right []string) int {
	limit := len(left)
	if len(right) < limit {
		limit = len(right)
	}
	for i := 0; i < limit; i++ {
		if left[i] < right[i] {
			return -1
		}
		if left[i] > right[i] {
			return 1
		}
	}
	if len(left) < len(right) {
		return -1
	}
	if len(left) > len(right) {
		return 1
	}
	return 0
}

func sortShares(shares []Share) {
	sort.Slice(shares, func(i, j int) bool {
		if shares[i].Holder != shares[j].Holder {
			return shares[i].Holder < shares[j].Holder
		}
		return shares[i].X < shares[j].X
	})
}

func holderList(shares []Share) []string {
	holders := make([]string, len(shares))
	for i, share := range shares {
		holders[i] = share.Holder
	}
	sort.Strings(holders)
	return holders
}

func evaluateAt(shares []Share, x int, prime int) int {
	p := int64(prime)
	target := int64(x)
	total := int64(0)
	for i, shareI := range shares {
		numerator := int64(1)
		denominator := int64(1)
		xI := int64(shareI.X)
		for j, shareJ := range shares {
			if i == j {
				continue
			}
			xJ := int64(shareJ.X)
			numerator = mod(numerator*mod(target-xJ, p), p)
			denominator = mod(denominator*mod(xI-xJ, p), p)
		}
		term := mod(int64(shareI.Y)*numerator%p*modInverse(denominator, p), p)
		total = mod(total+term, p)
	}
	return int(total)
}

func mod(value, prime int64) int64 {
	value %= prime
	if value < 0 {
		value += prime
	}
	return value
}

func modInverse(value, prime int64) int64 {
	t, nextT := int64(0), int64(1)
	r, nextR := prime, mod(value, prime)
	for nextR != 0 {
		quotient := r / nextR
		t, nextT = nextT, t-quotient*nextT
		r, nextR = nextR, r-quotient*nextR
	}
	return mod(t, prime)
}

func secretCommitment(caseID, epoch string, secret int) string {
	payload := fmt.Sprintf("%s\n%s\n%d\n", caseID, epoch, secret)
	sum := sha256.Sum256([]byte(payload))
	return "sha256:" + hex.EncodeToString(sum[:])
}

func modelRecord(model Model) []byte {
	encodeStrings := func(values []string) string {
		encoded := make([]string, len(values))
		for i, value := range values {
			encoded[i] = hex.EncodeToString([]byte(value))
		}
		return strings.Join(encoded, ",")
	}
	encodeChain := func(chain [][]string) string {
		edges := make([]string, len(chain))
		for i, holders := range chain {
			edges[i] = encodeStrings(holders)
		}
		return strings.Join(edges, ";")
	}
	policy := "0"
	if model.PolicyOK {
		policy = "1"
	}
	commitment := "0"
	if model.CommitmentOK {
		commitment = "1"
	}
	record := strings.Join([]string{
		hex.EncodeToString([]byte(model.Epoch)),
		strconv.Itoa(model.Secret),
		encodeStrings(holderList(model.Support)),
		encodeStrings(holderList(model.Outliers)),
		encodeStrings(holderList(model.Witness)),
		policy,
		commitment,
		strconv.Itoa(model.LineageDepth),
		encodeStrings(model.ContinuityHolders),
		encodeStrings(model.LineageEpochs),
		encodeChain(model.ContinuityChain),
	}, "|")
	return []byte(record)
}

func modelFrontierDigest(models []Model) string {
	records := make([][]byte, len(models))
	for i, model := range models {
		records[i] = modelRecord(model)
	}
	sort.Slice(records, func(i, j int) bool {
		return bytes.Compare(records[i], records[j]) < 0
	})
	hash := sha256.New()
	for _, record := range records {
		_, _ = hash.Write(record)
		_, _ = hash.Write([]byte{'\n'})
	}
	return "sha256:" + hex.EncodeToString(hash.Sum(nil))
}

func plainChain(chain [][]string) string {
	edges := make([]string, len(chain))
	for i, holders := range chain {
		edges[i] = strings.Join(holders, ",")
	}
	return strings.Join(edges, ";")
}

func evidenceDigest(report Report) string {
	reason := ""
	if report.Reason != nil {
		reason = *report.Reason
	}
	epoch := ""
	if report.SelectedEpoch != nil {
		epoch = *report.SelectedEpoch
	}
	secret := ""
	if report.SecretMod != nil {
		secret = *report.SecretMod
	}
	rejected := make([]string, len(report.Rejected))
	for i, item := range report.Rejected {
		rejected[i] = item.Epoch + "/" + item.Holder + ":" + item.Reason
	}
	payload := fmt.Sprintf(
		"%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%s\n%d\n%s\n%d\n%d\n%s\n%s\n",
		report.CaseID,
		report.Status,
		reason,
		epoch,
		strings.Join(report.LineageEpochs, ","),
		strings.Join(report.ContinuityHolders, ","),
		plainChain(report.ContinuityChain),
		strings.Join(report.SelectedHolders, ","),
		strings.Join(report.SupportHolders, ","),
		strings.Join(report.OutlierHolders, ","),
		report.SupportShareCount,
		secret,
		report.ValidShareCount,
		report.EvaluatedModelCount,
		report.ModelFrontierDigest,
		strings.Join(rejected, ","),
	)
	sum := sha256.Sum256([]byte(payload))
	return "sha256:" + hex.EncodeToString(sum[:])
}
