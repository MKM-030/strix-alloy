package main

import (
	"crypto/sha256"
	"fmt"
	"os"
	"path/filepath"
	"testing"
	"time"
)

func TestValidAdmission(t *testing.T) {
	p := filepath.Join(t.TempDir(), "admission.json")
	b := fmt.Sprintf("{\"version\":1,\"sessions\":[{\"id\":\"test\",\"instance\":\"fixture\",\"service_id\":\"voice\",\"token_sha256\":\"%x\",\"expires_at\":%d,\"peers\":[]}]}", sha256.Sum256([]byte("test-token")), time.Now().Unix()+60)
	if e := os.WriteFile(p, []byte(b), 0600); e != nil {
		t.Fatal(e)
	}
	r := Registry{Path: p}
	if _, ok := r.Authenticate("fixture:voice:test-token"); !ok {
		t.Fatal("currently admitted valid TURN token must authenticate")
	}
}
