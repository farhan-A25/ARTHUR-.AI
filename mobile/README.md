# ARTHUR — Mobile App

Expo + React Native + TypeScript client for the ARTHUR backend. One codebase
builds for iOS and Android.

## Quick start (development)

```bash
cd mobile
npm install
cp .env.example .env            # set EXPO_PUBLIC_ARTHUR_API_URL
npx expo start                  # scan the QR code with Expo Go
```

The app talks to the FastAPI backend (`/api/*`). For a local simulator,
`http://localhost:8000` works; for a physical device, use your machine's LAN IP.

### Physical device setup (same Wi-Fi)

1. In `arthur.config.json` (project root), set:
   - `api_host` to `0.0.0.0` (so the phone can reach the backend), and
   - `api_url` to this machine's LAN IP, e.g. `http://192.168.1.50:8000`.
2. Run `bash start-arthur.sh` (or double-click `start-arthur.bat`) — it writes
   `mobile/.env` with that URL automatically.
3. `npx expo start` and scan the QR code with Expo Go.
4. Sign in with your owner name + password on the login screen.

### Sign-in

The app opens on a **login screen**. Sessions are bearer tokens stored in the
device's secure keychain/keystore (`expo-secure-store`) and expire after
24 hours (`ARTHUR_SESSION_HOURS` on the backend). Any expired or revoked
session returns you to the login screen automatically. Sign out anytime from
the header button. First run: set the owner password via the ARTHUR console
or `ARTHUR_PASSWORD` env on the backend's first-run prompt.

## Screens

- **Chat** — send goals to ARTHUR, read plan replies.
- **Dashboard** — online status dot, current-user chip (+ Admin badge),
  projects, agents, task progress bars; polls `/api/*` every 3 s.
- **Approvals** — pending approval requests with one-tap Approve / Deny.
- **Projects** — project list + per-project task detail.

Push tokens are registered automatically on app start via
`POST /api/push/register` (`lib/notifications.ts`).

## Publishing to the App Store / Google Play

### 1. Developer accounts (yours — ARTHUR cannot do this for you)

1. **Apple Developer Program** — $99/year.
   Enroll at https://developer.apple.com/programs/enroll/ with your Apple ID.
   After enrollment, note your **Team ID** (Membership details page) and create
   the app record in **App Store Connect** → My Apps → **+** → New App
   (bundle ID `com.arthur.ai`, SKU of your choice). Note the **Apple ID**
   (numeric) of the app record.
2. **Google Play Console** — $25 one-time.
   Sign up at https://play.google.com/console/signup. Create an app
   (package `com.arthur.ai`), and create a **service account** in Google Cloud
   → IAM → Service Accounts with the *Service Account User* role, grant it
   access in Play Console → Users and permissions, and download the JSON key as
   `mobile/pc-api-key.json` (never commit this file).

### 2. Configure EAS

```bash
npm install -g eas-cli
eas login                       # your own Expo account
eas init                        # replace the placeholder projectId in app.json
```

Fill in `eas.json` → `submit.production`:
- iOS: your `appleId`, `appleTeamId`, `ascAppId`.
- Android: path to your `pc-api-key.json`.

### 3. Backend MUST be on a public HTTPS URL

Store builds cannot reach `http://localhost:8000`. Deploy the backend first,
e.g. on a small VPS:

```bash
# on the VPS, in ~/workspace/arthur-ai
docker-compose up -d --build api worker
# point https://api.yourdomain.com at the VPS (reverse proxy with TLS,
# e.g. Caddy or nginx + certbot)
```

Then set in EAS / your build environment:

```
EXPO_PUBLIC_ARTHUR_API_URL=https://api.yourdomain.com
```

### 4. Build

```bash
eas build --platform all --profile production
```

EAS produces an `.ipa` (iOS) and `.aab` (Android). Download them from the
EAS dashboard, or let `eas submit` upload directly:

```bash
eas submit --platform all --profile production
```

### 5. Screenshots & metadata checklist

- App name: **ARTHUR** · subtitle: "Your autonomous AI task assistant"
- Screenshots: 6.7" iPhone + 12.9" iPad + phone/tablet Android, showing
  Chat, Dashboard, Approvals (no real personal data visible).
- Privacy policy URL (required by both stores) — see "Hosting your privacy
  policy" below.
- iOS: answer the App Store Connect privacy questionnaire
  (notifications → device token; network → your API URL).
- Android: complete the Data safety form with the same disclosures;
  target the latest API level EAS requires.
- Content rating questionnaires on both stores (the app is a utility).

### 5b. Hosting your privacy policy

Both Apple and Google **require a public privacy-policy URL** at submission
— the listing is rejected without one. The repo ships a complete, store-ready
policy at `PRIVACY_POLICY.md` (repo root). Replace the placeholders
(`[APP OPERATOR]`, `[CONTACT EMAIL]`, `[LLM PROVIDER]`, `[HOSTING PROVIDER]`,
`[HOSTING REGION]`) with your real details, then publish it at a public URL.
Two easy options:

**Option A — serve it from your ARTHUR backend (recommended).**
The API already serves the file at `GET /privacy`, so once your backend is on
its public HTTPS URL (step 3 above), your policy URL is simply:

```
https://api.yourdomain.com/privacy
```

No extra work needed — just make sure the placeholders are filled in.

**Option B — GitHub Pages.** Push the repo (or just the policy) to GitHub,
enable Pages on the repo, and link the raw/rendered file URL, e.g.
`https://<you>.github.io/arthur-ai/PRIVACY_POLICY.md`.

Paste the final URL into App Store Connect ("Privacy Policy URL") and the
Google Play Console ("Privacy policy" link under App content).

### 6. Over-the-air updates

JS-only changes (no native modules / app.json changes) ship instantly:

```bash
eas update --branch production --message "Fix approvals refresh"
```

## Scripts

- `npm start` → `expo start`
- `npm run typecheck` → `tsc --noEmit`
