package exportacl

import (
	"sort"

	"nfsacld/internal/clientord"
	"nfsacld/internal/walops"
)

// ClientGrant is one NFS client ACL entry on an export path.
type ClientGrant struct {
	ClientID     string `json:"client_id"`
	Access       string `json:"access"`
	Squash       string `json:"squash"`
	AnonUID      int64  `json:"anon_uid"`
	AnonGID      int64  `json:"anon_gid"`
	Secure       bool   `json:"secure"`
	Specificity  int    `json:"specificity"`
	State        string `json:"state"`
}

// Export is one NFS export path with its client grants.
type Export struct {
	ExportPath string         `json:"export_path"`
	Clients    []*ClientGrant `json:"clients"`
}

// WaitEntry is one FIFO waitlist reservation.
type WaitEntry struct {
	ExportPath string `json:"export_path"`
	ClientID   string `json:"client_id"`
}

// Manager tracks live export ACLs and waitlist reservations.
type Manager struct {
	MaxClients     int64
	DefSquash      string
	DefAnonUID     int64
	DefAnonGID     int64
	DefAccess      string
	RequireSecure  bool
	exports        map[string]map[string]*ClientGrant
	wait           []WaitEntry
}

func New(maxClients int64, defSquash string, defAnonUID, defAnonGID int64, defAccess string, requireSecure bool) *Manager {
	return &Manager{
		MaxClients:    maxClients,
		DefSquash:     defSquash,
		DefAnonUID:    defAnonUID,
		DefAnonGID:    defAnonGID,
		DefAccess:     defAccess,
		RequireSecure: requireSecure,
		exports:       map[string]map[string]*ClientGrant{},
	}
}

func (m *Manager) Apply(op walops.Op) {
	switch op.Type {
	case "create_export":
		m.createExport(op)
	case "grant":
		m.grant(op)
	case "revoke":
		m.revoke(op)
	case "enqueue":
		m.enqueue(op)
	case "set_squash":
		m.setSquash(op)
	case "set_access":
		m.setAccess(op)
	case "destroy_export":
		m.destroy(op)
	case "reexport_pass":
		m.reexportPass()
	}
}

func (m *Manager) createExport(op walops.Op) {
	if _, ok := m.exports[op.ExportPath]; ok {
		return
	}
	m.exports[op.ExportPath] = map[string]*ClientGrant{}
}

func (m *Manager) stateOf(secure bool) string {
	if m.RequireSecure && !secure {
		return "insecure"
	}
	return "active"
}

func (m *Manager) newGrant(clientID, access, squash string, anonUID, anonGID int64, secure bool) *ClientGrant {
	if squash == "all_squash" {
		anonUID = m.DefAnonUID
		anonGID = m.DefAnonGID
	}
	return &ClientGrant{
		ClientID:    clientID,
		Access:      access,
		Squash:      squash,
		AnonUID:     anonUID,
		AnonGID:     anonGID,
		Secure:      secure,
		Specificity: clientord.Specificity(clientID),
		State:       m.stateOf(secure),
	}
}

func (m *Manager) grant(op walops.Op) {
	clients, ok := m.exports[op.ExportPath]
	if !ok {
		return
	}
	if _, exists := clients[op.ClientID]; exists {
		return
	}
	if int64(len(clients)) >= m.MaxClients {
		return
	}
	access := m.DefAccess
	if op.Access != nil {
		access = *op.Access
	}
	squash := m.DefSquash
	if op.Squash != nil {
		squash = *op.Squash
	}
	anonUID := m.DefAnonUID
	if op.AnonUID != nil {
		anonUID = *op.AnonUID
	}
	anonGID := m.DefAnonGID
	if op.AnonGID != nil {
		anonGID = *op.AnonGID
	}
	secure := true
	if op.Secure != nil {
		secure = *op.Secure
	}
	clients[op.ClientID] = m.newGrant(op.ClientID, access, squash, anonUID, anonGID, secure)
}

func (m *Manager) revoke(op walops.Op) {
	clients, ok := m.exports[op.ExportPath]
	if !ok {
		return
	}
	if _, exists := clients[op.ClientID]; !exists {
		return
	}
	delete(clients, op.ClientID)
	m.promote(op.ExportPath)
}

func (m *Manager) enqueue(op walops.Op) {
	for _, w := range m.wait {
		if w.ExportPath == op.ExportPath && w.ClientID == op.ClientID {
			return
		}
	}
	m.wait = append(m.wait, WaitEntry{ExportPath: op.ExportPath, ClientID: op.ClientID})
}

func (m *Manager) setSquash(op walops.Op) {
	clients, ok := m.exports[op.ExportPath]
	if !ok || op.Squash == nil {
		return
	}
	g, exists := clients[op.ClientID]
	if !exists {
		return
	}
	g.Squash = *op.Squash
	if g.Squash == "all_squash" {
		g.AnonUID = m.DefAnonUID
		g.AnonGID = m.DefAnonGID
	}
	g.State = m.stateOf(g.Secure)
}

func (m *Manager) setAccess(op walops.Op) {
	clients, ok := m.exports[op.ExportPath]
	if !ok || op.Access == nil {
		return
	}
	g, exists := clients[op.ClientID]
	if !exists {
		return
	}
	g.Access = *op.Access
}

func (m *Manager) destroy(op walops.Op) {
	delete(m.exports, op.ExportPath)
}

func (m *Manager) promote(exportPath string) bool {
	idx := -1
	for i, w := range m.wait {
		if w.ExportPath == exportPath {
			idx = i
			break
		}
	}
	if idx < 0 {
		return false
	}
	entry := m.wait[idx]
	clients, ok := m.exports[exportPath]
	if !ok {
		m.wait = append(m.wait[:idx], m.wait[idx+1:]...)
		return true
	}
	if int64(len(clients)) >= m.MaxClients {
		return false
	}
	if _, exists := clients[entry.ClientID]; exists {
		m.wait = append(m.wait[:idx], m.wait[idx+1:]...)
		return true
	}
	clients[entry.ClientID] = m.newGrant(entry.ClientID, m.DefAccess, m.DefSquash, m.DefAnonUID, m.DefAnonGID, true)
	m.wait = append(m.wait[:idx], m.wait[idx+1:]...)
	return true
}

func (m *Manager) reexportPass() {
	paths := make([]string, 0, len(m.exports))
	for p := range m.exports {
		paths = append(paths, p)
	}
	sort.Strings(paths)
	for _, path := range paths {
		for {
			clients := m.exports[path]
			if int64(len(clients)) >= m.MaxClients {
				break
			}
			hasMatch := false
			for _, w := range m.wait {
				if w.ExportPath == path {
					hasMatch = true
					break
				}
			}
			if !hasMatch {
				break
			}
			if !m.promote(path) {
				break
			}
		}
	}
}

// Snapshot returns sorted exports and the remaining waitlist.
func (m *Manager) Snapshot() ([]Export, []WaitEntry) {
	paths := make([]string, 0, len(m.exports))
	for p := range m.exports {
		paths = append(paths, p)
	}
	sort.Strings(paths)

	out := make([]Export, 0, len(paths))
	for _, path := range paths {
		clients := m.exports[path]
		list := make([]*ClientGrant, 0, len(clients))
		for _, g := range clients {
			list = append(list, g)
		}
		sort.Slice(list, func(i, j int) bool {
			if list[i].Specificity != list[j].Specificity {
				return list[i].Specificity > list[j].Specificity
			}
			return list[i].ClientID < list[j].ClientID
		})
		out = append(out, Export{ExportPath: path, Clients: list})
	}
	waitCopy := append([]WaitEntry{}, m.wait...)
	return out, waitCopy
}
