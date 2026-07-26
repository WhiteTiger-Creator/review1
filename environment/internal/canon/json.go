package canon

import (
        "bytes"
        "crypto/sha256"
        "encoding/hex"
        "encoding/json"
        "os"
        "sort"
)

func normalize(v any) (any, error) {
        switch t := v.(type) {
        case map[string]any:
                keys := make([]string, 0, len(t))
                for k := range t {
                        keys = append(keys, k)
                }
                sort.Strings(keys)
                out := make(map[string]any, len(t))
                for _, k := range keys {
                        nv, err := normalize(t[k])
                        if err != nil {
                                return nil, err
                        }
                        out[k] = nv
                }
                return out, nil
        case []any:
                out := make([]any, len(t))
                for i := range t {
                        nv, err := normalize(t[i])
                        if err != nil {
                                return nil, err
                        }
                        out[i] = nv
                }
                return out, nil
        case json.Number:
                if i, err := t.Int64(); err == nil {
                        return float64(i), nil
                }
                return t.Float64()
        default:
                return t, nil
        }
}

func CanonBytes(v any) ([]byte, error) {
        norm, err := normalize(v)
        if err != nil {
                return nil, err
        }
        return json.Marshal(norm)
}

func HexOf(v any) (string, error) {
        b, err := CanonBytes(v)
        if err != nil {
                return "", err
        }
        sum := sha256.Sum256(b)
        return hex.EncodeToString(sum[:]), nil
}

func ShaHex(b []byte) string {
        sum := sha256.Sum256(b)
        return hex.EncodeToString(sum[:])
}

func LoadJSON(path string) (any, error) {
        b, err := os.ReadFile(path)
        if err != nil {
                return nil, err
        }
        var v any
        dec := json.NewDecoder(bytes.NewReader(b))
        dec.UseNumber()
        if err := dec.Decode(&v); err != nil {
                return nil, err
        }
        return normalize(v)
}

func WritePretty(path string, v any) error {
        b, err := json.MarshalIndent(v, "", "  ")
        if err != nil {
                return err
        }
        b = append(b, '\n')
        return os.WriteFile(path, b, 0o644)
}

func AsU32(v any) uint32 {
        switch t := v.(type) {
        case float64:
                return uint32(t)
        case json.Number:
                i, _ := t.Int64()
                return uint32(i)
        case int:
                return uint32(t)
        case int64:
                return uint32(t)
        default:
                return 0
        }
}
