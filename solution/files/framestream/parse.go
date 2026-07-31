package framestream

import (
	"encoding/binary"
	"fmt"
	"net"
	"os"
)

// Packet is one captured TCP segment in arrival order.
type Packet struct {
	Index   int
	TsSec   uint32
	TsUsec  uint32
	SrcIP   net.IP
	DstIP   net.IP
	SrcPort uint16
	DstPort uint16
	Seq     uint32
	Ack     uint32
	Flags   uint8
	Payload []byte
}

func (p Packet) TsTotal() int64 {
	return int64(p.TsSec)*1_000_000 + int64(p.TsUsec)
}

// LoadPCAP reads a classic little-endian Ethernet/IPv4/TCP PCAP.
func LoadPCAP(path string) ([]Packet, error) {
	raw, err := os.ReadFile(path)
	if err != nil {
		return nil, err
	}
	if len(raw) < 24 {
		return nil, fmt.Errorf("pcap too short: %s", path)
	}
	magic := binary.LittleEndian.Uint32(raw[0:4])
	if magic != 0xa1b2c3d4 {
		return nil, fmt.Errorf("unsupported pcap magic in %s", path)
	}
	network := binary.LittleEndian.Uint32(raw[20:24])
	if network != 1 {
		return nil, fmt.Errorf("unsupported linktype %d in %s", network, path)
	}
	off := 24
	var out []Packet
	idx := 0
	for off+16 <= len(raw) {
		tsSec := binary.LittleEndian.Uint32(raw[off : off+4])
		tsUsec := binary.LittleEndian.Uint32(raw[off+4 : off+8])
		incl := int(binary.LittleEndian.Uint32(raw[off+8 : off+12]))
		off += 16
		if off+incl > len(raw) {
			return nil, fmt.Errorf("truncated packet in %s", path)
		}
		body := raw[off : off+incl]
		off += incl
		pkt, ok := parseFrame(body)
		if !ok {
			continue
		}
		pkt.Index = idx
		pkt.TsSec = tsSec
		pkt.TsUsec = tsUsec
		out = append(out, pkt)
		idx++
	}
	return out, nil
}

func parseFrame(body []byte) (Packet, bool) {
	var zero Packet
	if len(body) < 14+20+20 {
		return zero, false
	}
	ethertype := binary.BigEndian.Uint16(body[12:14])
	if ethertype != 0x0800 {
		return zero, false
	}
	ip := body[14:]
	vihl := ip[0]
	if vihl>>4 != 4 {
		return zero, false
	}
	ihl := int(vihl&0x0f) * 4
	if ihl < 20 || len(ip) < ihl+20 {
		return zero, false
	}
	totalLen := int(binary.BigEndian.Uint16(ip[2:4]))
	if totalLen < ihl || totalLen > len(ip) {
		totalLen = len(ip)
	}
	frag := binary.BigEndian.Uint16(ip[6:8])
	if frag&0x1fff != 0 || frag&0x2000 != 0 {
		return zero, false
	}
	if ip[9] != 6 {
		return zero, false
	}
	srcIP := append(net.IP(nil), ip[12:16]...)
	dstIP := append(net.IP(nil), ip[16:20]...)
	tcp := ip[ihl:totalLen]
	if len(tcp) < 20 {
		return zero, false
	}
	dataOff := int(tcp[12]>>4) * 4
	if dataOff < 20 || dataOff > len(tcp) {
		return zero, false
	}
	payload := append([]byte(nil), tcp[dataOff:]...)
	return Packet{
		SrcIP:   srcIP,
		DstIP:   dstIP,
		SrcPort: binary.BigEndian.Uint16(tcp[0:2]),
		DstPort: binary.BigEndian.Uint16(tcp[2:4]),
		Seq:     binary.BigEndian.Uint32(tcp[4:8]),
		Ack:     binary.BigEndian.Uint32(tcp[8:12]),
		Flags:   tcp[13],
		Payload: payload,
	}, true
}

func FlowKey(p Packet) string {
	return fmt.Sprintf("%s|%s|%d|%d", p.SrcIP.String(), p.DstIP.String(), p.SrcPort, p.DstPort)
}

func SwapKey(p Packet) string {
	return fmt.Sprintf("%s|%s|%d|%d", p.DstIP.String(), p.SrcIP.String(), p.DstPort, p.SrcPort)
}
