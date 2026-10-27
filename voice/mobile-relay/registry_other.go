//go:build !windows

package main

import "os"

func openRegistry(path string) (*os.File, error) { return os.Open(path) }
