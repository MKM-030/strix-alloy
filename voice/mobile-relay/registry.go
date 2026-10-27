package main

import (
	"bytes"
	"crypto/sha256"
	"crypto/subtle"
	"encoding/hex"
	"encoding/json"
	"errors"
	"io"
	"math"
	"net"
	"strings"
	"time"
)

var errPolicy = errors.New("relay policy denied")

const maxRegistryBytes = 262144

type Peer struct {
	IP   string `json:"ip"`
	Port int    `json:"port"`
}
type Session struct {
	ID          string  `json:"id"`
	Instance    string  `json:"instance"`
	ServiceID   string  `json:"service_id"`
	TokenSHA256 string  `json:"token_sha256"`
	ExpiresAt   float64 `json:"expires_at"`
	Peers       []Peer  `json:"peers"`
}
type RegistryFile struct {
	Version  int       `json:"version"`
	Sessions []Session `json:"sessions"`
}
type Registry struct{ Path string }

func strictValue(d *json.Decoder, depth int) error {
	if depth > 8 {
		return errPolicy
	}
	t, e := d.Token()
	if e != nil {
		return e
	}
	switch t {
	case json.Delim('{'):
		keys := map[string]bool{}
		for d.More() {
			key, e := d.Token()
			if e != nil {
				return e
			}
			k, ok := key.(string)
			if !ok || keys[k] {
				return errPolicy
			}
			keys[k] = true
			if e = strictValue(d, depth+1); e != nil {
				return e
			}
		}
		t, e = d.Token()
		if e != nil || t != json.Delim('}') {
			return errPolicy
		}
	case json.Delim('['):
		for d.More() {
			if e = strictValue(d, depth+1); e != nil {
				return e
			}
		}
		t, e = d.Token()
		if e != nil || t != json.Delim(']') {
			return errPolicy
		}
	}
	return nil
}
func validPart(s string, max int) bool {
	if len(s) == 0 || len(s) > max {
		return false
	}
	for _, r := range s {
		if r < 33 || r > 126 || r == ':' {
			return false
		}
	}
	return true
}
func (r *Registry) Load() ([]Session, error) {
	f, e := openRegistry(r.Path)
	if e != nil {
		return nil, errPolicy
	}
	defer f.Close()
	b, e := io.ReadAll(io.LimitReader(f, maxRegistryBytes+1))
	if e != nil || len(b) > maxRegistryBytes {
		return nil, errPolicy
	}
	d := json.NewDecoder(bytes.NewReader(b))
	if e = strictValue(d, 0); e != nil {
		return nil, errPolicy
	}
	if _, e = d.Token(); e != io.EOF {
		return nil, errPolicy
	}
	var rf RegistryFile
	d = json.NewDecoder(bytes.NewReader(b))
	d.DisallowUnknownFields()
	if e = d.Decode(&rf); e != nil || rf.Version != 1 || len(rf.Sessions) > 128 {
		return nil, errPolicy
	}
	ids := map[string]bool{}
	now := float64(time.Now().UnixNano()) / 1e9
	for _, s := range rf.Sessions {
		hash, e := hex.DecodeString(s.TokenSHA256)
		if !validPart(s.ID, 128) || !validPart(s.Instance, 255) || !validPart(s.ServiceID, 128) || len(hash) != 32 || e != nil || ids[s.ID] || len(s.Peers) > 32 || math.IsNaN(s.ExpiresAt) || math.IsInf(s.ExpiresAt, 0) || s.ExpiresAt > now+86400 {
			return nil, errPolicy
		}
		ids[s.ID] = true
		for _, p := range s.Peers {
			ip := net.ParseIP(p.IP)
			if ip == nil || ip.To4() == nil || ip.IsUnspecified() || ip.IsMulticast() || p.Port < 1 || p.Port > 65535 {
				return nil, errPolicy
			}
		}
	}
	return rf.Sessions, nil
}
func (r *Registry) Session(id string) (Session, bool) {
	ss, e := r.Load()
	if e != nil {
		return Session{}, false
	}
	now := float64(time.Now().UnixNano()) / 1e9
	for _, s := range ss {
		if s.ID == id && s.ExpiresAt > now {
			return s, true
		}
	}
	return Session{}, false
}
func identity(s Session) string {
	return s.ID + "\x00" + s.Instance + "\x00" + s.ServiceID + "\x00" + strings.ToLower(s.TokenSHA256)
}
func (r *Registry) Authenticate(username string) (Session, bool) {
	s, why := r.AuthenticateReason(username)
	return s, why == ""
}
func (r *Registry) AuthenticateReason(username string) (Session, string) {
	if len(username) > 8192 {
		return Session{}, "shape"
	}
	p := strings.SplitN(username, ":", 3)
	if len(p) != 3 || !validPart(p[0], 255) || !validPart(p[1], 128) || len(p[2]) == 0 {
		return Session{}, "shape"
	}
	for _, c := range p[2] {
		if c < 33 || c > 126 {
			return Session{}, "shape"
		}
	}
	ss, e := r.Load()
	if e != nil {
		return Session{}, "registry"
	}
	token := sha256.Sum256([]byte(p[2]))
	now := float64(time.Now().UnixNano()) / 1e9
	var found Session
	matches := 0
	inst, service, credential := false, false, false
	for _, s := range ss {
		hash, e := hex.DecodeString(s.TokenSHA256)
		same := subtle.ConstantTimeCompare(hash, token[:]) == 1
		if s.Instance == p[0] {
			inst = true
			if s.ServiceID == p[1] {
				service = true
				if e == nil && same {
					credential = true
					if s.ExpiresAt > now {
						found = s
						matches++
					}
				}
			}
		}
	}
	if matches == 1 {
		return found, ""
	}
	if matches > 1 {
		return Session{}, "ambiguous"
	}
	if !inst {
		return Session{}, "instance"
	}
	if !service {
		return Session{}, "service"
	}
	if !credential {
		return Session{}, "token"
	}
	return Session{}, "expired"
}
func boundID(s Session) string {
	h := sha256.Sum256([]byte(identity(s)))
	return hex.EncodeToString(h[:])
}
func (r *Registry) BoundSession(binding string) (Session, bool) {
	if len(binding) != 64 {
		return Session{}, false
	}
	ss, e := r.Load()
	if e != nil {
		return Session{}, false
	}
	now := float64(time.Now().UnixNano()) / 1e9
	for _, s := range ss {
		if s.ExpiresAt > now && subtle.ConstantTimeCompare([]byte(boundID(s)), []byte(binding)) == 1 {
			return s, true
		}
	}
	return Session{}, false
}
func (r *Registry) Allows(id string, a net.Addr) bool {
	s, ok := r.Session(id)
	if !ok {
		return false
	}
	return sessionAllows(s, a)
}
func sessionAllows(s Session, a net.Addr) bool {
	u, ok := a.(*net.UDPAddr)
	if !ok || u.IP.To4() == nil {
		return false
	}
	for _, p := range s.Peers {
		if p.Port == u.Port && net.ParseIP(p.IP).Equal(u.IP) {
			return true
		}
	}
	return false
}
