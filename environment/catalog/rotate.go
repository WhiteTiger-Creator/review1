package catalog

import (
	"bufio"
	"fmt"
	"os"
	"strconv"
	"strings"

	"gwc/store"
)

func Load(root string) (*store.Catalog, error) {
	uidByMark, suppByMark, dropMask, err := readMarks(root + "/config/principals.toml")
	if err != nil {
		return nil, err
	}
	pathByRef, markByRef, firstMark, err := readRefs(root + "/config/endpoints.toml")
	if err != nil {
		return nil, err
	}
	if firstMark == "" {
		firstMark = "kairo"
	}
	return &store.Catalog{
		ActiveMark: firstMark,
		DropMask:   dropMask,
		InodeGen:   1,
		PolicyGen:  1,
		UIDByMark:  uidByMark,
		SuppByMark: suppByMark,
		PathByRef:  pathByRef,
		MarkByRef:  markByRef,
	}, nil
}

func readMarks(path string) (map[string]int, map[string]uint32, uint32, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, 0, err
	}
	defer f.Close()
	uidOut := map[string]int{}
	suppOut := map[string]uint32{}
	var dropMask uint32 = 0x00ff
	sc := bufio.NewScanner(f)
	var cur string
	inTransition := false
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if line == "[transition]" {
			inTransition = true
			cur = ""
			continue
		}
		if strings.HasPrefix(line, "[[marks]]") {
			inTransition = false
			cur = ""
			continue
		}
		if inTransition && strings.HasPrefix(line, "drop_mask = ") {
			raw := strings.TrimSpace(strings.TrimPrefix(line, "drop_mask = "))
			v, err := parseUint(raw)
			if err == nil {
				dropMask = uint32(v)
			}
			continue
		}
		if strings.HasPrefix(line, "tag = ") {
			cur = strings.Trim(strings.TrimPrefix(line, "tag = "), "\"")
		}
		if strings.HasPrefix(line, "uid = ") && cur != "" {
			var uid int
			_, _ = fmt.Sscanf(strings.TrimPrefix(line, "uid = "), "%d", &uid)
			uidOut[cur] = uid
		}
		if strings.HasPrefix(line, "supp_mask = ") && cur != "" {
			raw := strings.TrimSpace(strings.TrimPrefix(line, "supp_mask = "))
			v, err := parseUint(raw)
			if err == nil {
				suppOut[cur] = uint32(v)
			}
		}
	}
	return uidOut, suppOut, dropMask, sc.Err()
}

func readRefs(path string) (map[string]string, map[string]string, string, error) {
	f, err := os.Open(path)
	if err != nil {
		return nil, nil, "", err
	}
	defer f.Close()
	pathByRef := map[string]string{}
	markByRef := map[string]string{}
	var firstMark string
	sc := bufio.NewScanner(f)
	var name, pth, mark string
	for sc.Scan() {
		line := strings.TrimSpace(sc.Text())
		if strings.HasPrefix(line, "[[refs]]") {
			if name != "" {
				pathByRef[name] = pth
				markByRef[name] = mark
			}
			name, pth, mark = "", "", ""
			continue
		}
		if strings.HasPrefix(line, "name = ") {
			name = strings.Trim(strings.TrimPrefix(line, "name = "), "\"")
		}
		if strings.HasPrefix(line, "path = ") {
			pth = strings.Trim(strings.TrimPrefix(line, "path = "), "\"")
		}
		if strings.HasPrefix(line, "mark_tag = ") {
			mark = strings.Trim(strings.TrimPrefix(line, "mark_tag = "), "\"")
			if firstMark == "" {
				firstMark = mark
			}
		}
	}
	if name != "" {
		pathByRef[name] = pth
		markByRef[name] = mark
	}
	return pathByRef, markByRef, firstMark, sc.Err()
}

func parseUint(raw string) (uint64, error) {
	raw = strings.TrimSpace(raw)
	if strings.HasPrefix(raw, "0x") || strings.HasPrefix(raw, "0X") {
		return strconv.ParseUint(raw[2:], 16, 32)
	}
	return strconv.ParseUint(raw, 10, 32)
}

func Shift(cat *store.Catalog, nextMark string) {
	cat.ActiveMark = nextMark
	cat.ShiftOpen = true
	store.OpenShiftWitness(cat)
	cat.PolicyGen++
}

func CloseShift(cat *store.Catalog) {
	store.CloseShiftWitness(cat)
}

func FinishCycle(cat *store.Catalog) {
	CloseShift(cat)
}
