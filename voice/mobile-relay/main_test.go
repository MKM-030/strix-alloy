package main

import (
	"context"
	"crypto/ecdsa"
	"crypto/elliptic"
	"crypto/rand"
	"crypto/sha256"
	"crypto/tls"
	"crypto/x509"
	"encoding/hex"
	"encoding/json"
	"github.com/pion/turn/v5"
	"io"
	"math/big"
	"net"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func fixture(t *testing.T, peers []Peer) (*Registry, string, Session) {
	t.Helper()
	path := filepath.Join(t.TempDir(), "registry.json")
	sum := sha256.Sum256([]byte("fixture-token-no-user-data"))
	s := Session{ID: "fixture-session", Instance: "fixture", ServiceID: "voice", TokenSHA256: hex.EncodeToString(sum[:]), ExpiresAt: float64(time.Now().Unix() + 120), Peers: peers}
	writeFixture(t, path, []Session{s})
	return &Registry{Path: path}, path, s
}
func writeFixture(t *testing.T, path string, s []Session) {
	t.Helper()
	b, e := json.Marshal(RegistryFile{Version: 1, Sessions: s})
	if e != nil {
		t.Fatal(e)
	}
	tmp := path + ".tmp"
	if e = os.WriteFile(tmp, b, 0600); e != nil {
		t.Fatal(e)
	}
	if e = os.Rename(tmp, path); e != nil {
		t.Fatal(e)
	}
}
func TestAdmissionRequiresCurrentExactToken(t *testing.T) {
	r, _, _ := fixture(t, nil)
	for _, tc := range []struct {
		name, user string
		want       bool
	}{
		{"valid", "fixture:voice:fixture-token-no-user-data", true},
		{"wrong token", "fixture:voice:wrong", false}, {"wrong service", "fixture:other:fixture-token-no-user-data", false},
		{"wrong instance", "other:voice:fixture-token-no-user-data", false}, {"malformed", "fixture", false}, {"empty", "fixture:voice:", false},
	} {
		t.Run(tc.name, func(t *testing.T) {
			s, ok := r.Authenticate(tc.user)
			if ok != tc.want {
				t.Fatalf("admission=%v want %v", ok, tc.want)
			}
			if ok && s.ID != "fixture-session" {
				t.Fatal("wrong session binding")
			}
		})
	}
}
func TestExpiryRemovalAndStrictRegistry(t *testing.T) {
	r, path, s := fixture(t, []Peer{{IP: "127.0.0.1", Port: 54321}})
	if !r.Allows(s.ID, &net.UDPAddr{IP: net.ParseIP("127.0.0.1"), Port: 54321}) {
		t.Fatal("valid peer denied")
	}
	s.ExpiresAt = float64(time.Now().Unix() - 1)
	writeFixture(t, path, []Session{s})
	if _, ok := r.Authenticate("fixture:voice:fixture-token-no-user-data"); ok {
		t.Fatal("expired auth accepted")
	}
	if r.Allows(s.ID, &net.UDPAddr{IP: net.ParseIP("127.0.0.1"), Port: 54321}) {
		t.Fatal("expired traffic accepted")
	}
	writeFixture(t, path, nil)
	if _, ok := r.Authenticate("fixture:voice:fixture-token-no-user-data"); ok {
		t.Fatal("removed auth accepted")
	}
	for _, data := range []string{"{\"version\":1,\"sessions\":[],\"unknown\":1}", "{\"version\":2,\"sessions\":[]}", "{\"version\":1,\"sessions\":[]} {}"} {
		if e := os.WriteFile(path, []byte(data), 0600); e != nil {
			t.Fatal(e)
		}
		if _, e := r.Load(); e == nil {
			t.Fatal("invalid registry accepted")
		}
	}
}
func TestExactPeerAndCrossSession(t *testing.T) {
	r, path, s := fixture(t, []Peer{{IP: "127.0.0.1", Port: 54321}})
	other := s
	other.ID = "other"
	other.Peers = []Peer{{IP: "127.0.0.1", Port: 54322}}
	other.TokenSHA256 = hex.EncodeToString(make([]byte, 32))
	writeFixture(t, path, []Session{s, other})
	for _, tc := range []struct {
		id, ip string
		port   int
		want   bool
	}{{s.ID, "127.0.0.1", 54321, true}, {s.ID, "127.0.0.1", 54322, false}, {other.ID, "127.0.0.1", 54321, false}, {"missing", "127.0.0.1", 54321, false}, {s.ID, "8.8.8.8", 54321, false}} {
		if got := r.Allows(tc.id, &net.UDPAddr{IP: net.ParseIP(tc.ip), Port: tc.port}); got != tc.want {
			t.Fatalf("peer policy got %v want %v", got, tc.want)
		}
	}
}
func TestGuardedRelayEnforcesBothDirectionsAndRemoval(t *testing.T) {
	good, e := net.ListenPacket("udp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer good.Close()
	bad, e := net.ListenPacket("udp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer bad.Close()
	r, path, s := fixture(t, []Peer{{IP: "127.0.0.1", Port: good.LocalAddr().(*net.UDPAddr).Port}})
	g, e := NewGenerator(r, net.ParseIP("127.0.0.1"))
	if e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	c, addr, e := g.AllocatePacketConn(turn.AllocateListenerConfig{Network: "udp4", UserID: boundID(s)})
	if e != nil {
		t.Fatal(e)
	}
	defer c.Close()
	if _, e = c.WriteTo([]byte("bad"), bad.LocalAddr()); e == nil {
		t.Fatal("wrong destination port accepted")
	}
	if _, e = c.WriteTo([]byte("synthetic"), good.LocalAddr()); e != nil {
		t.Fatal(e)
	}
	b := make([]byte, 128)
	_ = good.SetReadDeadline(time.Now().Add(time.Second))
	n, _, e := good.ReadFrom(b)
	if e != nil || string(b[:n]) != "synthetic" {
		t.Fatal("allowed write not delivered")
	}
	_, _ = bad.WriteTo([]byte("blocked"), addr)
	_, _ = good.WriteTo([]byte("allowed"), addr)
	_ = c.SetReadDeadline(time.Now().Add(time.Second))
	n, _, e = c.ReadFrom(b)
	if e != nil || string(b[:n]) != "allowed" {
		t.Fatal("inbound exact-peer guard failed")
	}
	writeFixture(t, path, nil)
	if _, e = c.WriteTo([]byte("expired"), good.LocalAddr()); e == nil {
		t.Fatal("removed admission still writable")
	}
}
func TestAllocationLimitsAndNoTCPRelay(t *testing.T) {
	r, _, s := fixture(t, nil)
	g, e := NewGenerator(r, net.ParseIP("127.0.0.1"))
	if e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	for i := 0; i < 4; i++ {
		if _, _, e = g.AllocatePacketConn(turn.AllocateListenerConfig{Network: "udp4", UserID: boundID(s)}); e != nil {
			t.Fatal(e)
		}
	}
	if _, _, e = g.AllocatePacketConn(turn.AllocateListenerConfig{Network: "udp4", UserID: boundID(s)}); e == nil {
		t.Fatal("per-session allocation quota bypassed")
	}
	if _, _, e = g.AllocateListener(turn.AllocateListenerConfig{Network: "tcp4", UserID: boundID(s)}); e == nil {
		t.Fatal("TCP allocation allowed")
	}
	if _, e = g.AllocateConn(turn.AllocateConnConfig{UserID: boundID(s)}); e == nil {
		t.Fatal("TCP connect allowed")
	}
}
func TestRealTCPAllocationBidirectionalSynthetic(t *testing.T) {
	peer, e := net.ListenPacket("udp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer peer.Close()
	r, path, _ := fixture(t, []Peer{{IP: "127.0.0.1", Port: peer.LocalAddr().(*net.UDPAddr).Port}})
	srv, e := StartRelay("127.0.0.1:0", "", net.ParseIP("127.0.0.1"), "voice.local", r)
	if e != nil {
		t.Fatal(e)
	}
	defer srv.Close()
	raw, e := net.DialTimeout("tcp4", srv.Addr().String(), time.Second)
	if e != nil {
		t.Fatal(e)
	}
	defer raw.Close()
	client, e := turn.NewClient(&turn.ClientConfig{TURNServerAddr: srv.Addr().String(), Conn: turn.NewSTUNConn(raw), Username: "fixture:voice:fixture-token-no-user-data", Password: "oauth", LoggerFactory: quietLogger{}})
	if e != nil {
		t.Fatal(e)
	}
	defer client.Close()
	if e = client.Listen(); e != nil {
		t.Fatal(e)
	}
	allocation, e := client.Allocate()
	if e != nil {
		t.Fatal(e)
	}
	defer allocation.Close()
	if _, e = allocation.WriteTo([]byte("synthetic-out"), peer.LocalAddr()); e != nil {
		t.Fatal(e)
	}
	b := make([]byte, 128)
	_ = peer.SetReadDeadline(time.Now().Add(2 * time.Second))
	n, from, e := peer.ReadFrom(b)
	if e != nil || string(b[:n]) != "synthetic-out" {
		t.Fatal("TURN output not delivered")
	}
	if _, e = peer.WriteTo([]byte("synthetic-in"), from); e != nil {
		t.Fatal(e)
	}
	_ = allocation.SetReadDeadline(time.Now().Add(2 * time.Second))
	n, _, e = allocation.ReadFrom(b)
	if e != nil || string(b[:n]) != "synthetic-in" {
		t.Fatal("TURN input not returned")
	}
	writeFixture(t, path, nil)
	time.Sleep(400 * time.Millisecond)
	if srv.generator.Count() != 0 {
		t.Fatal("removed admission allocation not closed")
	}
}

func TestAuthBindingRejectsRegistryReplacement(t *testing.T) {
	r, path, s := fixture(t, nil)
	oldBinding := boundID(s)
	sum := sha256.Sum256([]byte("different-token"))
	s.TokenSHA256 = hex.EncodeToString(sum[:])
	writeFixture(t, path, []Session{s})
	g, e := NewGenerator(r, net.ParseIP("127.0.0.1"))
	if e != nil {
		t.Fatal(e)
	}
	defer g.Close()
	if _, _, e = g.AllocatePacketConn(turn.AllocateListenerConfig{Network: "udp4", UserID: oldBinding}); e == nil {
		t.Fatal("old authenticated identity inherited replacement session")
	}
}
func TestRealWrongCredentialRejected(t *testing.T) {
	r, _, _ := fixture(t, nil)
	srv, e := StartRelay("127.0.0.1:0", "", net.ParseIP("127.0.0.1"), "voice.local", r)
	if e != nil {
		t.Fatal(e)
	}
	defer srv.Close()
	raw, e := net.DialTimeout("tcp4", srv.Addr().String(), time.Second)
	if e != nil {
		t.Fatal(e)
	}
	defer raw.Close()
	client, e := turn.NewClient(&turn.ClientConfig{TURNServerAddr: srv.Addr().String(), Conn: turn.NewSTUNConn(raw), Username: "fixture:voice:wrong", Password: "oauth", LoggerFactory: quietLogger{}})
	if e != nil {
		t.Fatal(e)
	}
	defer client.Close()
	if e = client.Listen(); e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 2*time.Second)
	defer cancel()
	a, e := client.AllocateWithContext(ctx)
	if e == nil {
		a.Close()
		t.Fatal("wrong credential acquired allocation")
	}
	if srv.generator.Count() != 0 {
		t.Fatal("rejected credential consumed allocation")
	}
}
func TestRealTLSAllocationSynthetic(t *testing.T) {
	peer, e := net.ListenPacket("udp4", "127.0.0.1:0")
	if e != nil {
		t.Fatal(e)
	}
	defer peer.Close()
	r, _, _ := fixture(t, []Peer{{IP: "127.0.0.1", Port: peer.LocalAddr().(*net.UDPAddr).Port}})
	srv, e := StartRelay("127.0.0.1:0", "", net.ParseIP("127.0.0.1"), "voice.local", r)
	if e != nil {
		t.Fatal(e)
	}
	defer srv.Close()
	key, e := ecdsa.GenerateKey(elliptic.P256(), rand.Reader)
	if e != nil {
		t.Fatal(e)
	}
	template := &x509.Certificate{SerialNumber: big.NewInt(1), NotBefore: time.Now().Add(-time.Minute), NotAfter: time.Now().Add(time.Hour), DNSNames: []string{"fixture.test"}, KeyUsage: x509.KeyUsageDigitalSignature | x509.KeyUsageCertSign, ExtKeyUsage: []x509.ExtKeyUsage{x509.ExtKeyUsageServerAuth}, BasicConstraintsValid: true, IsCA: true}
	der, e := x509.CreateCertificate(rand.Reader, template, template, &key.PublicKey, key)
	if e != nil {
		t.Fatal(e)
	}
	cert := tls.Certificate{Certificate: [][]byte{der}, PrivateKey: key}
	roots := x509.NewCertPool()
	parsed, e := x509.ParseCertificate(der)
	if e != nil {
		t.Fatal(e)
	}
	roots.AddCert(parsed)
	front, e := tls.Listen("tcp4", "127.0.0.1:0", &tls.Config{Certificates: []tls.Certificate{cert}, MinVersion: tls.VersionTLS12})
	if e != nil {
		t.Fatal(e)
	}
	defer front.Close()
	proxyDone := make(chan struct{})
	go func() {
		defer close(proxyDone)
		c, e := front.Accept()
		if e != nil {
			return
		}
		defer c.Close()
		back, e := net.DialTimeout("tcp4", srv.Addr().String(), time.Second)
		if e != nil {
			return
		}
		defer back.Close()
		go func() { _, _ = io.Copy(back, c); back.Close() }()
		_, _ = io.Copy(c, back)
	}()
	raw, e := tls.DialWithDialer(&net.Dialer{Timeout: 2 * time.Second}, "tcp4", front.Addr().String(), &tls.Config{RootCAs: roots, ServerName: "fixture.test", MinVersion: tls.VersionTLS12})
	if e != nil {
		t.Fatal(e)
	}
	defer raw.Close()
	client, e := turn.NewClient(&turn.ClientConfig{TURNServerAddr: front.Addr().String(), Conn: turn.NewSTUNConn(raw), Username: "fixture:voice:fixture-token-no-user-data", Password: "oauth", LoggerFactory: quietLogger{}})
	if e != nil {
		t.Fatal(e)
	}
	defer client.Close()
	if e = client.Listen(); e != nil {
		t.Fatal(e)
	}
	ctx, cancel := context.WithTimeout(context.Background(), 3*time.Second)
	defer cancel()
	a, e := client.AllocateWithContext(ctx)
	if e != nil {
		t.Fatal(e)
	}
	defer a.Close()
	if _, e = a.WriteTo([]byte("tls-synthetic"), peer.LocalAddr()); e != nil {
		t.Fatal(e)
	}
	b := make([]byte, 128)
	peer.SetReadDeadline(time.Now().Add(2 * time.Second))
	n, from, e := peer.ReadFrom(b)
	if e != nil || string(b[:n]) != "tls-synthetic" {
		t.Fatal("TLS TURN outbound missing")
	}
	peer.WriteTo([]byte("tls-echo"), from)
	a.SetReadDeadline(time.Now().Add(2 * time.Second))
	n, _, e = a.ReadFrom(b)
	if e != nil || string(b[:n]) != "tls-echo" {
		t.Fatal("TLS TURN inbound missing")
	}
	a.Close()
	client.Close()
	raw.Close()
	front.Close()
	select {
	case <-proxyDone:
	case <-time.After(time.Second):
		t.Fatal("TLS proxy did not close")
	}
}
