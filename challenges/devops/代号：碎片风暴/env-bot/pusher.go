package main

import (
	"bytes"
	"fmt"
	"math/rand"
	"net/http"
	"os"
	"sync"
	"time"
)

func generateFragments(flag string) []string {
	if len(flag) == 0 {
		return nil
	}

	var fragments []string
	length := len(flag)
	r := rand.New(rand.NewSource(time.Now().UnixNano()))

	for i := 0; i < 200; i++ {
		start := r.Intn(length - 2)
		if start < 0 {
			start = 0
		}
		fragLen := r.Intn(6) + 3
		end := start + fragLen
		if end > length {
			end = length
		}

		frag := flag[start:end]
		if len(frag) > 0 {
			fragments = append(fragments, frag)
		}
	}

	r.Shuffle(len(fragments), func(i, j int) {
		fragments[i], fragments[j] = fragments[j], fragments[i]
	})

	return fragments
}

func main() {
	flag := os.Getenv("Flag")
	if flag == "" {
		flag = os.Getenv("FLAG")
	}
	if flag == "" {
		flag = "moectf{this-is-a-meaningless-string}"
	}

	transport := &http.Transport{
		MaxIdleConns:        100,
		IdleConnTimeout:     90 * time.Second,
		MaxIdleConnsPerHost: 100,
	}
	client := &http.Client{
		Transport: transport,
		Timeout:   2 * time.Second,
	}

	targetURL := "http://127.0.0.1:3000"

	for {
		fmt.Printf("[+] 正在生成新一轮随机碎片...\n")
		fragments := generateFragments(flag)

		var wg sync.WaitGroup

		for _, frag := range fragments {
			wg.Add(1)
			go func(f string) {
				defer wg.Done()
				resp, err := client.Post(targetURL, "text/plain", bytes.NewBufferString(f))
				if err != nil {
					return
				}
				_ = resp.Body.Close()
			}(frag)

			time.Sleep(1 * time.Millisecond)
		}

		wg.Wait()
		time.Sleep(5 * time.Second)
	}
}
