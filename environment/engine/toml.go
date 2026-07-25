package engine

import (
	"bufio"
	"fmt"
	"os"
	"reflect"
	"strconv"
	"strings"
)

func loadTOML(path string, cfg any) error {
	f, err := os.Open(path)
	if err != nil {
		return err
	}
	defer f.Close()
	val := reflect.ValueOf(cfg)
	if val.Kind() != reflect.Ptr || val.Elem().Kind() != reflect.Struct {
		return fmt.Errorf("cfg must be pointer to struct")
	}
	fields := map[string]reflect.Value{}
	t := val.Elem().Type()
	for i := 0; i < t.NumField(); i++ {
		fields[t.Field(i).Tag.Get("toml")] = val.Elem().Field(i)
	}
	scan := bufio.NewScanner(f)
	for scan.Scan() {
		line := strings.TrimSpace(scan.Text())
		if line == "" || strings.HasPrefix(line, "#") {
			continue
		}
		parts := strings.SplitN(line, "=", 2)
		if len(parts) != 2 {
			continue
		}
		key := strings.TrimSpace(parts[0])
		value := strings.Trim(strings.TrimSpace(parts[1]), "\"")
		field, ok := fields[key]
		if !ok {
			continue
		}
		switch field.Kind() {
		case reflect.String:
			field.SetString(value)
		case reflect.Int:
			if n, err := strconv.Atoi(value); err == nil {
				field.SetInt(int64(n))
			}
		}
	}
	return scan.Err()
}
