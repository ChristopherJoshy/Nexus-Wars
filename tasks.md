# Tasks

## Setup auth
- Generate `BETTER_AUTH_SECRET` (32+ chars, `openssl rand -base64 32`)
- Create Google OAuth credentials (client ID + secret)
- Update `services/web/.env.local`

## End-to-end test full flow
- Start Docker stack (postgres + minio + worker)
- Create team via API
- Submit a bot (upload to MinIO, enqueue validation job)
- Verify worker picks up job and runs validation
- Verify DB updated with result

## Verify canvas replay viewer
- Generate a real match replay (via e2e test or direct engine run)
- Load it in the viewer
- Fix any rendering issues

## Optional hardening
- Add `clone_newuser` + drop to nobody in `deploy/nsjail.cfg`
