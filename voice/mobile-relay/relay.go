package main

import (
	"context"
	"encoding/json"
	"errors"
	"github.com/pion/logging"
	"github.com/pion/turn/v5"
	"io"
	"net"
	"net/http"
	"sync"
	"sync/atomic"
	"time"
)

const maxPayload = 8192
const maxConnLifetime = time.Hour

type quietLogger struct{}

func (quietLogger) NewLogger(string) logging.LeveledLogger { return silentLog{} }

type silentLog struct{}

func (silentLog) Trace(string)          {}
func (silentLog) Tracef(string, ...any) {}
func (silentLog) Debug(string)          {}
func (silentLog) Debugf(string, ...any) {}
func (silentLog) Info(string)           {}
func (silentLog) Infof(string, ...any)  {}
func (silentLog) Warn(string)           {}
func (silentLog) Warnf(string, ...any)  {}
func (silentLog) Error(string)          {}
func (silentLog) Errorf(string, ...any) {}

type counters struct {
	Out, In, OutBytes, InBytes, Denied, AuthDenied, AuthAccepted, Allocated atomic.Uint64
	Reasons                                                                 [8]atomic.Uint64
}

var reasonNames = []string{"shape", "instance", "service", "token", "expired", "ambiguous", "registry", "realm"}

type Generator struct {
	registry *Registry
	ip       net.IP
	local    map[string]bool
	mu       sync.Mutex
	conns    map[*guardedPacket]bool
	closed   bool
	stop     chan struct{}
	stats    counters
}

func NewGenerator(r *Registry, ip net.IP) (*Generator, error) {
	if ip == nil || ip.To4() == nil || ip.IsUnspecified() || ip.IsMulticast() {
		return nil, errPolicy
	}
	local := map[string]bool{}
	as, e := net.InterfaceAddrs()
	if e != nil {
		return nil, errPolicy
	}
	for _, a := range as {
		v, _, e := net.ParseCIDR(a.String())
		if e == nil && v.To4() != nil {
			local[v.To4().String()] = true
		}
	}
	if !local[ip.To4().String()] {
		return nil, errPolicy
	}
	g := &Generator{registry: r, ip: ip.To4(), local: local, conns: map[*guardedPacket]bool{}, stop: make(chan struct{})}
	go func() {
		t := time.NewTicker(250 * time.Millisecond)
		defer t.Stop()
		for {
			select {
			case <-g.stop:
				return
			case <-t.C:
				g.sweep()
			}
		}
	}()
	return g, nil
}
func (g *Generator) Validate() error {
	if g.registry == nil || g.ip == nil {
		return errPolicy
	}
	return nil
}
func (g *Generator) AllocatePacketConn(c turn.AllocateListenerConfig) (net.PacketConn, net.Addr, error) {
	if c.Network != "udp4" || c.RequestedPort != 0 {
		return nil, nil, errPolicy
	}
	s, ok := g.registry.BoundSession(c.UserID)
	if !ok {
		return nil, nil, errPolicy
	}
	g.mu.Lock()
	defer g.mu.Unlock()
	count := 0
	for x := range g.conns {
		if x.id == s.ID {
			count++
		}
	}
	if g.closed || len(g.conns) >= 8 || count >= 4 {
		return nil, nil, errPolicy
	}
	raw, e := net.ListenPacket("udp4", net.JoinHostPort(g.ip.String(), "0"))
	if e != nil {
		return nil, nil, errPolicy
	}
	p := &guardedPacket{PacketConn: raw, g: g, id: s.ID, identity: identity(s), created: time.Now(), rateUpdated: time.Now(), tokens: 1048576}
	g.conns[p] = true
	g.stats.Allocated.Add(1)
	return p, raw.LocalAddr(), nil
}
func (g *Generator) AllocateListener(turn.AllocateListenerConfig) (net.Listener, net.Addr, error) {
	return nil, nil, errPolicy
}
func (g *Generator) AllocateConn(turn.AllocateConnConfig) (net.Conn, error) { return nil, errPolicy }
func (g *Generator) Count() int                                             { g.mu.Lock(); defer g.mu.Unlock(); return len(g.conns) }
func (g *Generator) sweep() {
	g.mu.Lock()
	cs := make([]*guardedPacket, 0, len(g.conns))
	for c := range g.conns {
		cs = append(cs, c)
	}
	g.mu.Unlock()
	for _, c := range cs {
		if _, ok := c.active(); !ok {
			_ = c.Close()
		}
	}
}
func (g *Generator) Close() {
	g.mu.Lock()
	if g.closed {
		g.mu.Unlock()
		return
	}
	g.closed = true
	close(g.stop)
	cs := make([]*guardedPacket, 0, len(g.conns))
	for c := range g.conns {
		cs = append(cs, c)
	}
	g.mu.Unlock()
	for _, c := range cs {
		_ = c.Close()
	}
}

type guardedPacket struct {
	net.PacketConn
	g            *Generator
	id, identity string
	created      time.Time
	once         sync.Once
	rateMu       sync.Mutex
	rateUpdated  time.Time
	tokens       float64
}

func (p *guardedPacket) active() (Session, bool) {
	s, ok := p.g.registry.Session(p.id)
	return s, ok && identity(s) == p.identity && time.Since(p.created) < maxConnLifetime
}
func (p *guardedPacket) allowed(s Session, a net.Addr) bool {
	u, ok := a.(*net.UDPAddr)
	return ok && p.g.local[u.IP.To4().String()] && sessionAllows(s, a)
}
func (p *guardedPacket) rateAllow(n int) bool {
	p.rateMu.Lock()
	defer p.rateMu.Unlock()
	now := time.Now()
	p.tokens += now.Sub(p.rateUpdated).Seconds() * 1048576
	if p.tokens > 1048576 {
		p.tokens = 1048576
	}
	p.rateUpdated = now
	if float64(n) > p.tokens {
		return false
	}
	p.tokens -= float64(n)
	return true
}
func (p *guardedPacket) WriteTo(b []byte, a net.Addr) (int, error) {
	s, ok := p.active()
	if !ok {
		_ = p.Close()
		return 0, errPolicy
	}
	if len(b) > maxPayload || !p.allowed(s, a) || !p.rateAllow(len(b)) {
		p.g.stats.Denied.Add(1)
		return 0, errPolicy
	}
	n, e := p.PacketConn.WriteTo(b, a)
	if e == nil {
		p.g.stats.Out.Add(1)
		p.g.stats.OutBytes.Add(uint64(n))
	}
	return n, e
}
func (p *guardedPacket) ReadFrom(b []byte) (int, net.Addr, error) {
	var buf [maxPayload + 1]byte
	for {
		s, ok := p.active()
		if !ok {
			_ = p.Close()
			return 0, nil, errPolicy
		}
		n, a, e := p.PacketConn.ReadFrom(buf[:])
		if e != nil {
			return 0, nil, e
		}
		s, ok = p.active()
		if !ok {
			_ = p.Close()
			return 0, nil, errPolicy
		}
		if n > maxPayload || n > len(b) || !p.allowed(s, a) || !p.rateAllow(n) {
			p.g.stats.Denied.Add(1)
			continue
		}
		copy(b, buf[:n])
		p.g.stats.In.Add(1)
		p.g.stats.InBytes.Add(uint64(n))
		return n, a, nil
	}
}
func (p *guardedPacket) Close() error {
	var e error
	p.once.Do(func() { e = p.PacketConn.Close(); p.g.mu.Lock(); delete(p.g.conns, p); p.g.mu.Unlock() })
	return e
}

type cappedListener struct {
	net.Listener
	registry *Registry
	mu       sync.Mutex
	conns    map[*cappedConn]bool
	closed   bool
	stop     chan struct{}
}
type cappedConn struct {
	net.Conn
	owner        *cappedListener
	once         sync.Once
	created      time.Time
	id, identity string
}

func (c *cappedConn) Close() error {
	var e error
	c.once.Do(func() { e = c.Conn.Close(); c.owner.mu.Lock(); delete(c.owner.conns, c); c.owner.mu.Unlock() })
	return e
}
func newCappedListener(l net.Listener, r *Registry) *cappedListener {
	c := &cappedListener{Listener: l, registry: r, conns: map[*cappedConn]bool{}, stop: make(chan struct{})}
	go func() {
		t := time.NewTicker(250 * time.Millisecond)
		defer t.Stop()
		for {
			select {
			case <-c.stop:
				return
			case <-t.C:
				c.sweep()
			}
		}
	}()
	return c
}
func (l *cappedListener) Accept() (net.Conn, error) {
	for {
		raw, e := l.Listener.Accept()
		if e != nil {
			return nil, e
		}
		l.mu.Lock()
		if l.closed {
			l.mu.Unlock()
			_ = raw.Close()
			return nil, net.ErrClosed
		}
		if len(l.conns) >= 16 {
			l.mu.Unlock()
			_ = raw.Close()
			continue
		}
		c := &cappedConn{Conn: raw, owner: l, created: time.Now()}
		l.conns[c] = true
		l.mu.Unlock()
		_ = raw.SetDeadline(time.Now().Add(30 * time.Second))
		return c, nil
	}
}
func (l *cappedListener) authorize(a net.Addr, s Session) {
	l.mu.Lock()
	defer l.mu.Unlock()
	for c := range l.conns {
		if c.RemoteAddr().String() == a.String() {
			c.id = s.ID
			c.identity = identity(s)
			until := time.Unix(0, int64(s.ExpiresAt*1e9))
			cap := c.created.Add(maxConnLifetime)
			if until.After(cap) {
				until = cap
			}
			_ = c.SetDeadline(until)
		}
	}
}
func (l *cappedListener) permission(a net.Addr, ip net.IP) bool {
	l.mu.Lock()
	var id, expected string
	for c := range l.conns {
		if c.RemoteAddr().String() == a.String() {
			id = c.id
			expected = c.identity
		}
	}
	l.mu.Unlock()
	s, ok := l.registry.Session(id)
	if !ok || identity(s) != expected {
		return false
	}
	for _, p := range s.Peers {
		if net.ParseIP(p.IP).Equal(ip) {
			return true
		}
	}
	return false
}
func (l *cappedListener) sweep() {
	l.mu.Lock()
	type view struct {
		c            *cappedConn
		id, identity string
		created      time.Time
	}
	list := []view{}
	for c := range l.conns {
		list = append(list, view{c, c.id, c.identity, c.created})
	}
	l.mu.Unlock()
	for _, v := range list {
		if v.id == "" {
			if time.Since(v.created) >= 30*time.Second {
				_ = v.c.Close()
			}
			continue
		}
		s, ok := l.registry.Session(v.id)
		if !ok || identity(s) != v.identity || time.Since(v.created) >= maxConnLifetime {
			_ = v.c.Close()
		}
	}
}
func (l *cappedListener) Close() error {
	l.mu.Lock()
	if l.closed {
		l.mu.Unlock()
		return nil
	}
	l.closed = true
	close(l.stop)
	cs := []*cappedConn{}
	for c := range l.conns {
		cs = append(cs, c)
	}
	l.mu.Unlock()
	e := l.Listener.Close()
	for _, c := range cs {
		_ = c.Close()
	}
	return e
}
func (l *cappedListener) Count() int { l.mu.Lock(); defer l.mu.Unlock(); return len(l.conns) }

type Relay struct {
	server         *turn.Server
	generator      *Generator
	listener       *cappedListener
	health         *http.Server
	healthListener net.Listener
	once           sync.Once
	StartupID      string
}

func loopbackAddress(s string) bool {
	h, _, e := net.SplitHostPort(s)
	ip := net.ParseIP(h)
	return e == nil && ip != nil && ip.IsLoopback()
}
func StartRelay(listen, health string, ip net.IP, realm string, r *Registry) (*Relay, error) {
	if !loopbackAddress(listen) || (health != "" && !loopbackAddress(health)) || !validPart(realm, 128) {
		return nil, errPolicy
	}
	if _, e := r.Load(); e != nil {
		return nil, errPolicy
	}
	g, e := NewGenerator(r, ip)
	if e != nil {
		return nil, e
	}
	raw, e := net.Listen("tcp4", listen)
	if e != nil {
		g.Close()
		return nil, errors.New("relay listener unavailable")
	}
	relay := &Relay{generator: g, listener: newCappedListener(raw, r)}
	// Bind every listener before Pion starts accepting. No ready state on port conflict.
	if health != "" {
		relay.healthListener, e = net.Listen("tcp4", health)
		if e != nil {
			relay.Close()
			return nil, errors.New("health listener unavailable")
		}
	}
	server, e := turn.NewServer(turn.ServerConfig{
		Realm: realm, LoggerFactory: quietLogger{}, AllocationLifetime: 2 * time.Minute, PermissionTimeout: 5 * time.Minute, ChannelBindTimeout: 10 * time.Minute, InboundMTU: maxPayload,
		AuthHandler: func(a *turn.RequestAttributes) (string, []byte, bool) {
			if a.Realm != realm {
				g.stats.Reasons[7].Add(1)
				return "", nil, false
			}
			s, why := r.AuthenticateReason(a.Username)
			if why != "" {
				for i, v := range reasonNames {
					if v == why {
						g.stats.Reasons[i].Add(1)
					}
				}
				return "", nil, false
			}
			return boundID(s), turn.GenerateAuthKey(a.Username, realm, "oauth"), true
		},
		EventHandler: turn.EventHandler{OnAuth: func(src, dst net.Addr, protocol, username, realm, method string, verdict bool) {
			if verdict {
				g.stats.AuthAccepted.Add(1)
			} else {
				g.stats.AuthDenied.Add(1)
			}
		}, OnAllocationCreated: func(src, dst net.Addr, protocol, id, realm string, relayAddr net.Addr, port int) {
			if s, ok := r.BoundSession(id); ok {
				relay.listener.authorize(src, s)
			}
		}},
		ListenerConfigs: []turn.ListenerConfig{{Listener: relay.listener, RelayAddressGenerator: g, PermissionHandler: relay.listener.permission}},
	})
	if e != nil {
		relay.Close()
		return nil, errors.New("TURN startup failed")
	}
	relay.server = server
	return relay, nil
}
func (r *Relay) StartHealth(startupID string) {
	r.StartupID = startupID
	if r.healthListener == nil {
		return
	}
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, q *http.Request) {
		if q.Method != http.MethodGet {
			w.WriteHeader(http.StatusMethodNotAllowed)
			return
		}
		w.Header().Set("Content-Type", "application/json")
		w.Header().Set("Cache-Control", "no-store")
		reasons := map[string]uint64{}
		for i, name := range reasonNames {
			reasons[name] = r.generator.stats.Reasons[i].Load()
		}
		_ = json.NewEncoder(w).Encode(map[string]any{"status": "ready", "startup_id": r.StartupID, "connections": r.listener.Count(), "allocations": r.generator.Count(), "packets_to_peer": r.generator.stats.Out.Load(), "packets_from_peer": r.generator.stats.In.Load(), "packets_denied": r.generator.stats.Denied.Load(), "auth_denied": r.generator.stats.AuthDenied.Load(), "accepted_auth": r.generator.stats.AuthAccepted.Load(), "rejected_auth": r.generator.stats.AuthDenied.Load(), "rejected_auth_reasons": reasons, "allocations_total": r.generator.stats.Allocated.Load(), "bytes_to_peer": r.generator.stats.OutBytes.Load(), "bytes_from_peer": r.generator.stats.InBytes.Load()})
	})
	r.health = &http.Server{Handler: mux, ReadHeaderTimeout: 2 * time.Second, ReadTimeout: 3 * time.Second, WriteTimeout: 3 * time.Second, IdleTimeout: 10 * time.Second, MaxHeaderBytes: 4096, ErrorLog: nil}
	go func() { _ = r.health.Serve(r.healthListener) }()
}
func (r *Relay) Addr() net.Addr { return r.listener.Addr() }
func (r *Relay) Close() {
	r.once.Do(func() {
		if r.health != nil {
			ctx, cancel := context.WithTimeout(context.Background(), time.Second)
			_ = r.health.Shutdown(ctx)
			cancel()
		}
		if r.healthListener != nil {
			_ = r.healthListener.Close()
		}
		if r.listener != nil {
			_ = r.listener.Close()
		}
		if r.server != nil {
			_ = r.server.Close()
		}
		if r.generator != nil {
			r.generator.Close()
		}
	})
}

var _ io.Reader = (*cappedConn)(nil)
