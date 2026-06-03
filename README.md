# Landom landing pages

Five static landing pages are served by one Docker container running Nginx.
Email leads are collected by a small FastAPI service and stored in MySQL.
LandOm SDK events are loaded from the CDN on every page and ingested by the same FastAPI service.

## Local run

```bash
docker compose up -d --build
```

Default routes:

- `http://localhost/landom`
- `http://localhost/attune`
- `http://localhost/sian`
- `http://localhost/soom`
- `http://localhost/moyo`

If port 80 is already occupied, run:

```bash
LANDING_HTTP_PORT=8080 docker compose up -d --build
```

Then use `http://localhost:8080/landom`.

## Lead capture

Each page sends final CTA email submissions to:

```text
POST /api/leads
```

The MySQL table is `lead_signups`, with these main fields:

- `service`: `landom`, `attune`, `sian`, `soom`, or `moyo`
- `email`
- `language`
- `cta_id`
- `page_path`
- `source_url`
- `created_at` (KST, MySQL `+09:00`)

To inspect captured leads through the API:

```bash
curl -H "X-Admin-Token: local-dev-token" http://localhost/api/leads
curl -H "X-Admin-Token: local-dev-token" "http://localhost/api/leads?service=soom"
```

Set `LEADS_ADMIN_TOKEN` in production.

## LandOm SDK

Each landing page loads the SDK through the CDN:

```html
<script src="https://unpkg.com/landom-sdk/dist/landom-sdk.umd.js" defer></script>
<script src="/assets/landom-sdk-init.js" defer></script>
```

`/assets/landom-sdk-init.js` is generated when the Nginx container starts, so SDK project keys can stay in Compose environment variables instead of being hard-coded into the HTML files.

Configure these values in `.env`:

```text
LANDOM_SDK_ENDPOINT=/api/v1/events
LANDOM_SDK_API_KEY=...
ATTUNE_SDK_API_KEY=...
SIAN_SDK_API_KEY=...
SOOM_SDK_API_KEY=...
MOYO_SDK_API_KEY=...
```

SDK batches are received at:

```text
POST /api/v1/events
```

The SDK sends `X-Project-Key` during normal flushes. Beacon fallback requests can include `apiKey` in the body. Events are stored in `sdk_sessions` and `sdk_events`, keyed by service and session ID.

## Meta Pixel

The pages load `/assets/meta-pixel.js`, which is generated from environment variables when the Nginx container starts. This keeps the pixel ID out of the HTML files and lets local/staging traffic stay disabled.

```text
META_PIXEL_ENABLED=false
META_PIXEL_ID=your-meta-pixel-id
```

Set `META_PIXEL_ENABLED=true` in production to enable `PageView` events. Successful email submissions also send a Meta `Lead` event through `assets/lead-capture.js` with service-specific names such as `landom_email_reservation`, `attune_email_reservation`, and `soom_email_reservation`.

## Nginx Proxy Manager

Yes, each page can be assigned to a different domain through Nginx Proxy Manager.

If NPM runs in Docker, connect the NPM container to this Compose network:

```bash
docker network connect landom-landing-pages <nginx-proxy-manager-container-name>
```

For a path-based setup, create a Proxy Host that forwards to:

- Scheme: `http`
- Forward Hostname/IP: `landing-pages`
- Forward Port: `80`

Then each domain can point to one of these upstream paths: `/landom`, `/attune`, `/sian`, `/soom`, `/moyo`.

For a clean root-domain setup such as `https://attune.example.com` showing the Attune page at `/`, add this kind of custom Nginx location in that Proxy Host's Advanced section:

```nginx
location = / {
    proxy_pass http://landing-pages/attune;
}

location /assets/ {
    proxy_pass http://landing-pages/assets/;
}
```

Change `/attune` to `/landom`, `/sian`, `/soom`, or `/moyo` for each domain.
