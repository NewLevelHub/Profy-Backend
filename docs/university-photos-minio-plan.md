# University photos via self-hosted MinIO (S3-compatible storage)

## Context

Product wants each university card to show a photo. The backend currently
has **zero image/file handling** anywhere (no upload endpoint, no storage
config, no `python-multipart`/`boto3` dependency). Two options were
discussed with the user: link to externally-hosted photos (zero infra) vs.
self-hosting an S3-compatible store so photos never depend on a third-party
site staying up. **User chose: self-host MinIO** as a new container in the
existing docker-compose stack, admin uploads the file directly (not "paste a
URL you found on Wikipedia").

This touches real production infrastructure, so the plan below is built from
reading the actual deploy setup, not assumptions:

- Three separate environments, each with **enforced unique container
  names** to avoid DNS collisions on the shared edge network — see
  `docker-compose.dev.yml`'s comment *"NEVER db/redis — those resolve to
  PROD on edge net"*. `db`/`redis` (prod) vs `profi_db_dev`/`profi_redis_dev`
  (dev). A new `minio` service must follow the same discipline:
  `profi_minio_prod` (prod) / `profi_minio_dev` (dev), local dev can keep
  the short name `minio` (its own isolated compose project, not on the
  shared edge network).
- **One shared edge nginx container** (`profi_nginx_prod`) serves *both*
  `profy.newlevelhub.kz` (prod) and `dev.profy.newlevelhub.kz` (dev) from a
  single `nginx.prod.conf`, deployed by two separate CD pipelines
  (`cd.yml`, `cd-dev.yml`) that both restart this same container
  (flock-guarded against each other).
- `docs/nginx-prod-points-to-dev-incident.md` records a real outage: a
  **static `upstream { server X }` block** crash-loops the whole shared edge
  nginx (both domains, not just one) the moment container `X` doesn't exist
  yet at nginx startup. The fix already adopted everywhere else in
  `nginx.prod.conf` is **lazy per-request resolution**:
  `set $x_upstream http://container:port; proxy_pass $x_upstream;` (relying
  on the existing `resolver 127.0.0.11 valid=10s ipv6=off;`). Any new
  `location` added for MinIO **must** use this same pattern — never a static
  `upstream{}` block or a bare `proxy_pass http://profi_minio_prod:9000;`.
- CD scripts start `db`/`redis` via `up -d db redis` (no
  `--force-recreate`, so data volumes survive redeploys) as a separate step
  from `api`/`nginx` (which *are* force-recreated every deploy). MinIO needs
  the same "start once, never force-recreate" treatment so uploaded photos
  aren't touched by app/nginx redeploys.

## Design

- **Storage**: MinIO container, one persistent volume per environment,
  reachable only on the internal docker network (S3 API port 9000 not
  published to the internet).
- **Public URL shape**: `https://<domain>/media/<object_key>` — edge nginx
  proxies `/media/` to the MinIO container's S3 API for a fixed public
  bucket (`university-photos`), so photos are served from the same domain/TLS
  cert as the rest of the API, no CORS, no extra DNS/cert needed. Bucket is
  made public-read (via a bucket policy set at app startup), so this proxy
  is a plain reverse proxy, not an authenticated one.
- **Backend talks to MinIO via `boto3`**, using `endpoint_url=S3_ENDPOINT_URL`
  — this is the standard S3-compatible pattern, so if MinIO is ever swapped
  for AWS S3/R2/Yandex later, it's an env var change, not a code change
  (same philosophy as `LLM_BASE_URL` for OpenAI-compatible providers).
- **Upload flow**: new admin endpoint takes a multipart file, validates it
  (content-type `image/*`, size cap), **re-encodes/resizes it with Pillow**
  before storing, uploads to MinIO under a random key, sets
  `University.photo_url` to the public URL, in one request — no separate
  "paste URL" step.
- **Disk usage on the VPS**: MinIO stores files on the same VPS disk as
  Postgres/Redis (self-hosted, not offloaded like a managed S3 would be).
  At this project's scale (dozens of universities, not user-generated
  content at volume) that's fine in absolute terms — but only if uploads
  are normalized on the way in, since an admin could otherwise upload a
  multi-MB phone photo per university. Mitigate by resizing every upload to
  a fixed max dimension and re-encoding to JPEG/WebP at a fixed quality
  (e.g. max 1200px on the long side, JPEG quality ~80) in
  `storage_service.upload_university_photo` before the `put_object` call —
  this bounds each stored object to roughly tens of KB regardless of the
  original, keeping total storage in the low tens of MB even at 100+
  universities.

## Changes

### 1. Dependencies (`requirements.txt`)
- `boto3` — S3-compatible client.
- `python-multipart` — required by FastAPI for `UploadFile`/`File(...)`
  (not currently a dependency anywhere in this repo — grep confirms no
  multipart usage exists yet).
- `Pillow` — resize/compress photos on upload so disk usage on the VPS
  stays small and predictable regardless of what an admin uploads (see
  disk-usage discussion below).

### 2. Config (`app/config.py`, `.env.example`)
Add, mirroring the existing `RESEND_API_KEY`-style optional-with-warning
pattern:
```python
S3_ENDPOINT_URL: str = ""      # e.g. http://profi_minio_prod:9000 (internal)
S3_ACCESS_KEY: str = ""
S3_SECRET_KEY: str = ""
S3_BUCKET_NAME: str = "university-photos"
S3_PUBLIC_BASE_URL: str = ""   # e.g. https://profy.newlevelhub.kz/media
```
Document in `.env.example` next to the existing Resend block. Real values
go in `.env.production`/`.env.development` on the server (not committed),
same as `RESEND_API_KEY` today.

### 3. New `app/services/storage_service.py`
- A module-level `boto3.client("s3", endpoint_url=..., aws_access_key_id=...,
  aws_secret_access_key=..., region_name="us-east-1")` — MinIO ignores
  region but boto3 requires one set.
- `ensure_bucket() -> None`: idempotent `create_bucket` (catch
  `BucketAlreadyOwnedByYou`/`BucketAlreadyExists`) + `put_bucket_policy`
  granting anonymous `s3:GetObject` on the bucket (public-read for images
  only, uploads still require the admin endpoint + auth). Called once from
  `app/main.py`'s `lifespan`, wrapped in try/except that logs a warning
  instead of crashing startup if S3 isn't configured yet (same
  fail-soft posture as the email service when `RESEND_API_KEY` is blank).
- `upload_university_photo(file_bytes: bytes, content_type: str) -> str`:
  validates `content_type` starts with `image/` and `len(file_bytes)` is
  under an upload cap (e.g. 8 MB, generous since it's re-encoded anyway),
  opens it with `PIL.Image.open`, resizes so the long side is capped (e.g.
  1200px, skip if already smaller) preserving aspect ratio, re-encodes to
  JPEG at a fixed quality (e.g. 80) into an in-memory buffer — this is also
  a normalization step (whatever format was uploaded, storage is always
  `.jpg`), builds key `f"{uuid4()}.jpg"`, calls `put_object` via
  `asyncio.to_thread` (same async-wrapping pattern already used for
  `resend.Emails.send` in `email_service.py`, since both Pillow's encode and
  boto3's `put_object` are blocking calls), returns
  `f"{settings.S3_PUBLIC_BASE_URL}/{key}"`. Raises `ValueError` on
  validation/decode failure (matches this codebase's existing convention of
  service-layer `ValueError` → router-level `HTTPException`).

### 4. Model + migration
- `app/models/university.py`: add
  `photo_url: Mapped[str | None] = mapped_column(Text, nullable=True)`
  (`Text`, not `String(N)`, matching `source_url` — object-store URLs can be
  long).
- New Alembic migration, `ALTER TABLE universities ADD COLUMN photo_url
  TEXT NULL`. Resolve the actual current head via `alembic heads` at
  implementation time (this repo has multiple migration branches) — do not
  guess `down_revision`.

### 5. Schemas
- `app/schemas/university.py::UniversityBrief` — add
  `photo_url: str | None = None` (reused inside `ProgramBrief`/
  `ProgramDetail`, so both public endpoints get it for free).
- `app/schemas/admin_university.py`:
  - `AdminUniversityDetail` — add `photo_url: str | None`.
  - `AdminUniversityListItem` — add `photo_url: str | None` (so the admin
    list can show which universities still need a photo).

### 6. Admin endpoints (`app/routers/admin.py`, `app/services/admin_university_service.py`)
- New `POST /admin/universities/{university_id}/photo`, multipart
  `file: UploadFile`, gated by the existing `Depends(get_current_admin_user)`.
  Reads bytes, calls `storage_service.upload_university_photo(...)`, sets
  `university.photo_url` + `updated_at`, commits, returns
  `AdminUniversityDetail` — mirrors the shape of the existing
  `update_university` (fetch-or-404, mutate, commit, refresh, return).
- `list_universities` — add `photo_url=u.photo_url` to the
  `AdminUniversityListItem(...)` construction (it's built field-by-field,
  not via `from_attributes`, so this is a required one-line addition, not
  automatic).
- `AdminUniversityUpdateRequest` does **not** need a `photo_url` field —
  photos are set via the new upload endpoint, not PATCH, since the file
  itself has to go somewhere (a PATCH with a raw URL would let an admin
  paste an arbitrary external URL, defeating the "own storage" goal decided
  above; skip it unless the user wants a manual-override escape hatch too).

### 7. Infra — MinIO service (all three compose files)
- `docker-compose.yml` (local): service `minio`, image `minio/minio`,
  `command: server /data --console-address ":9001"`, env
  `MINIO_ROOT_USER`/`MINIO_ROOT_PASSWORD` (local dummy values in `.env`),
  volume `minio_data:/data`, `ports: ["9000:9000", "9001:9001"]` (console
  reachable directly in local dev), healthcheck via `mc ready` or a simple
  TCP check.
- `docker-compose.dev.yml`: service key `minio_dev`, `container_name:
  profi_minio_dev`, same image/command, env via `.env.development`, volume
  `minio_data_dev:/data`, **not** exposing ports publicly (internal network
  only — reached through nginx). Join **both** `profi_network_dev` and
  `profi_edge` — confirmed from the file that `api_dev` itself is on both
  networks for exactly this reason (so the shared edge nginx, which is not
  part of `profi_network_dev`, can reach it); `minio_dev` needs the same
  dual membership.
- `docker-compose.prod.yml`: service key `minio`, `container_name:
  profi_minio_prod`, env via `.env.production`, volume
  `minio_data_prod:/data`, on `profi_network` (internal only).

### 8. Infra — nginx (`nginx/local.conf` and both server blocks in `nginx.prod.conf`)
Add, using the **lazy-resolve pattern** (mandatory per the incident doc —
no static `upstream{}`):
```nginx
location /media/ {
    set $minio_upstream http://profi_minio_prod:9000;   # per-block container name
    rewrite ^/media/(.*)$ /university-photos/$1 break;
    proxy_pass $minio_upstream;
    proxy_set_header Host $host;
}
```
- In the `profy.newlevelhub.kz` server block → `profi_minio_prod`.
- In the `dev.profy.newlevelhub.kz` server block → `profi_minio_dev`.
- In `nginx/local.conf` → `minio:9000` (single local compose project, static
  reference is fine there — it's not the shared multi-env edge nginx the
  incident doc is about).

### 9. Infra — CD workflows (`cd.yml`, `cd-dev.yml`)
- Add `minio`/`minio_dev` to the existing `up -d db redis` line (the
  "ensure running, don't force-recreate" step) in both `deploy_production`
  and `deploy_development` jobs, so redeploys never touch the photo volume.
- After that line, call `storage_service.ensure_bucket()` — either let
  `app/main.py`'s lifespan do it automatically on the next API start
  (simplest, no extra CD step), or add an explicit
  `docker compose exec api python -c "from app.services.storage_service import ensure_bucket; ensure_bucket()"`
  step if bucket creation needs to happen before the API container is
  considered healthy. Prefer the lifespan approach — one less CD step to
  maintain, consistent with how this repo already handles startup checks
  (DB `SELECT 1` in the same lifespan).

### 10. Env vars to add on the server (not committed — document in `.env.example` only)
`.env.production` / `.env.development` need real values for
`S3_ENDPOINT_URL` (internal container URL, e.g.
`http://profi_minio_prod:9000`), `S3_ACCESS_KEY`, `S3_SECRET_KEY` (set
these as the MinIO root credentials or a dedicated MinIO user — user's
call at deploy time), `S3_BUCKET_NAME=university-photos`,
`S3_PUBLIC_BASE_URL` (`https://profy.newlevelhub.kz/media` /
`https://dev.profy.newlevelhub.kz/media`).

## Verification

1. **Local**: `docker compose up -d`, confirm `minio` container healthy,
   hit `POST /admin/universities/{id}/photo` with a real admin token and an
   image file, confirm `200` + `photo_url` in the response resolves
   (`curl -I http://localhost/media/<key>` → `200`, correct `Content-Type`).
2. Confirm `GET /admin/universities/{id}` and the public university/program
   endpoints (`UniversityBrief`) return the new `photo_url`.
3. Confirm re-running `alembic upgrade head` locally applies the new
   column cleanly against the current head.
4. **Nginx config sanity** before touching the shared server: validate
   `nginx.prod.conf` syntax exactly the way the incident doc's diagnostic
   commands do (`docker run --rm ... nginx -t`), and confirm every new
   `location /media/` block uses `set $var ...; proxy_pass $var;` — never a
   bare `proxy_pass http://container:port;` or an `upstream{}` block, to
   avoid repeating the crash-loop incident.
5. After deploying dev first (`cd-dev.yml` runs on push to `dev`), verify
   `https://dev.profy.newlevelhub.kz/media/<key>` before doing the same on
   prod.
