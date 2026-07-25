package protocol

import (
	"bufio"
	"encoding/json"
	"fmt"
	"io"
	"os"
	"os/exec"
	"path/filepath"
	"time"
)

type Envelope struct {
	Type string          `json:"type"`
	Raw  json.RawMessage `json:"-"`
}

func EncodeLine(w io.Writer, v any) error {
	b, err := json.Marshal(v)
	if err != nil {
		return err
	}
	_, err = w.Write(append(b, '\n'))
	return err
}

func DecodeOrders(line []byte) (map[string]any, error) {
	var m map[string]any
	if err := json.Unmarshal(line, &m); err != nil {
		return nil, err
	}
	t, _ := m["type"].(string)
	if t != "orders" && t != "end_ack" {
		return nil, fmt.Errorf("expected orders, got %s", t)
	}
	return m, nil
}

type BotSession struct {
	cmd    *exec.Cmd
	stdin  io.WriteCloser
	stdout *bufio.Scanner
	dir    string
}

func CompileBot(botDir, outBin string) error {
	cmd := exec.Command("go", "build", "-o", outBin, ".")
	cmd.Dir = botDir
	cmd.Env = append(os.Environ(), "CGO_ENABLED=0", "GOFLAGS=-mod=mod")
	out, err := cmd.CombinedOutput()
	if err != nil {
		return fmt.Errorf("compile failed: %v: %s", err, string(out))
	}
	return nil
}

func StartBot(bin string, workDir string) (*BotSession, error) {
	cmd := exec.Command(bin)
	cmd.Dir = workDir
	stdin, err := cmd.StdinPipe()
	if err != nil {
		return nil, err
	}
	stdout, err := cmd.StdoutPipe()
	if err != nil {
		return nil, err
	}
	cmd.Stderr = io.Discard
	if err := cmd.Start(); err != nil {
		return nil, err
	}
	sc := bufio.NewScanner(stdout)
	buf := make([]byte, 0, 64*1024)
	sc.Buffer(buf, 1024*1024)
	return &BotSession{cmd: cmd, stdin: stdin, stdout: sc, dir: workDir}, nil
}

func (s *BotSession) Send(v any) error {
	return EncodeLine(s.stdin, v)
}

func (s *BotSession) Recv(timeout time.Duration) (map[string]any, error) {
	type result struct {
		m   map[string]any
		err error
	}
	ch := make(chan result, 1)
	go func() {
		if !s.stdout.Scan() {
			if err := s.stdout.Err(); err != nil {
				ch <- result{nil, err}
				return
			}
			ch <- result{nil, io.EOF}
			return
		}
		m, err := DecodeOrders(s.stdout.Bytes())
		ch <- result{m, err}
	}()
	select {
	case r := <-ch:
		return r.m, r.err
	case <-time.After(timeout):
		return nil, fmt.Errorf("bot response timeout")
	}
}

func (s *BotSession) Close() {
	if s.stdin != nil {
		_ = s.stdin.Close()
	}
	if s.cmd != nil && s.cmd.Process != nil {
		_ = s.cmd.Process.Kill()
		_, _ = s.cmd.Process.Wait()
	}
}

func TempBotBinary(botDir string) (string, func(), error) {
	tmp, err := os.MkdirTemp("", "defensebot-bin-*")
	if err != nil {
		return "", nil, err
	}
	bin := filepath.Join(tmp, "defensebot")
	if err := CompileBot(botDir, bin); err != nil {
		_ = os.RemoveAll(tmp)
		return "", nil, err
	}
	cleanup := func() { _ = os.RemoveAll(tmp) }
	return bin, cleanup, nil
}
