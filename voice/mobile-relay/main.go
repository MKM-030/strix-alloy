package main

import (
	"encoding/json"
	"flag"
	"fmt"
	"io"
	"net"
	"os"
	"os/signal"
	"path/filepath"
	"regexp"
	"syscall"
)

func main() {
	listen := flag.String("listen", "127.0.0.1:8872", "Loopback TURN TCP listener")
	health := flag.String("health", "127.0.0.1:8873", "Loopback health listener (empty disables)")
	relayIP := flag.String("relay-ip", "", "Assigned local IPv4 relay address")
	registry := flag.String("registry", "", "Absolute admitted-session registry path")
	realm := flag.String("realm", "voice.local", "TURN realm")
	startupID := flag.String("startup-id", "", "Safe opaque startup identifier")
	eof := flag.Bool("exit-on-stdin-eof", false, "Close relay when parent stdin pipe closes")
	flag.Parse()
	if flag.NArg() != 0 || !filepath.IsAbs(*registry) || !regexp.MustCompile("^[A-Za-z0-9_-]{16,64}$").MatchString(*startupID) {
		fmt.Fprintln(os.Stderr, "invalid relay startup configuration")
		os.Exit(2)
	}
	r, e := StartRelay(*listen, *health, net.ParseIP(*relayIP), *realm, &Registry{Path: *registry})
	if e != nil {
		fmt.Fprintln(os.Stderr, "relay startup failed")
		os.Exit(1)
	}
	r.StartHealth(*startupID)
	defer r.Close()
	_ = json.NewEncoder(os.Stdout).Encode(map[string]any{"status": "ready", "startup_id": *startupID})
	done := make(chan struct{}, 1)
	if *eof {
		go func() {
			_, _ = io.Copy(io.Discard, os.Stdin)
			select {
			case done <- struct{}{}:
			default:
			}
		}()
	}
	sig := make(chan os.Signal, 1)
	signal.Notify(sig, os.Interrupt, syscall.SIGTERM)
	defer signal.Stop(sig)
	select {
	case <-done:
	case <-sig:
	}
	r.Close()
	_ = json.NewEncoder(os.Stdout).Encode(map[string]string{"status": "stopped", "startup_id": *startupID})
}
