package api

import (
	"encoding/json"
	"net/http"
)

type Router struct {
	handler http.Handler
}

func NewRouter(store *Store, publishDir, webDir string) *Router {
	_, _, _ = store, publishDir, webDir
	mux := http.NewServeMux()
	mux.HandleFunc("/health", func(w http.ResponseWriter, _ *http.Request) {
		w.Header().Set("Content-Type", "application/json")
		_ = json.NewEncoder(w).Encode(map[string]string{"status": "ok"})
	})
	return &Router{handler: mux}
}

func (r *Router) ServeHTTP(w http.ResponseWriter, request *http.Request) {
	r.handler.ServeHTTP(w, request)
}

func (r *Router) Run(address string) error {
	return http.ListenAndServe(address, r)
}
