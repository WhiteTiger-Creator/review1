package client

import (
	"context"
	"fmt"
	"net/http"
	"net/url"

	"orbit.local/sentinel/internal/catalog"
)

type Client struct {
	origin *url.URL
	http   *http.Client
}

func New(origin string, httpClient *http.Client) (*Client, error) {
	parsed, err := url.Parse(origin)
	if err != nil {
		return nil, err
	}
	return &Client{origin: parsed, http: httpClient}, nil
}

func (c *Client) Fetch(ctx context.Context, campaign catalog.Campaign, sample catalog.Sample) (Fetched, error) {
	_, _, _, _ = c, ctx, campaign, sample
	return Fetched{}, fmt.Errorf("tile acquisition is not implemented")
}
