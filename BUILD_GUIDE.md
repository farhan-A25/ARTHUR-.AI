# ARTHUR — Build & Run Guide
**Owner: Mohammed Farhan** · App v1.1 · September 30, 2026

## What this is
The complete ARTHUR app built from your files: Python backend (manager +
specialist agents, task queue, approvals, memory, security), web dashboard,
and the Expo mobile app (Chat, Dashboard, Approvals, Projects) with
sign-in.

## Run it (3 steps)
1. Unzip anywhere, open a terminal in the `arthur-ai` folder.
2. **Mac/Linux:** `bash start-arthur.sh` · **Windows:** double-click `start-arthur.bat`
   - First run creates the environment and installs everything automatically.
   - First run asks for the **owner name** (use `Mohammed Farhan`) and sets the owner password.
3. Open the dashboard at http://localhost:8000, or run the phone app below.

## Phone app (Expo Go, free, no store needed)
```bash
cd mobile && npm install && npx expo start
```
Scan the QR code with **Expo Go** (iOS/Android). Sign in on the login
screen with your owner name + password.

**Physical phone on your Wi-Fi:** in `arthur.config.json` set
`api_host` to `0.0.0.0` and `api_url` to this computer's LAN IP
(e.g. `http://192.168.1.50:8000`), then re-run the launcher —
it wires the app automatically.

## Security included
- Login screen → bearer token sessions (24 h expiry), stored in the
  phone's secure keychain/keystore — never in plain storage.
- Expired/revoked sessions return to login automatically; sign-out button
  in the header.
- Backend: bcrypt passwords, rate-limited login, lockout on brute force,
  encrypted secrets, audit-logged role changes. You are the sole admin.

## Verified before packaging
- `expo-doctor`: 21/21 checks passed · `tsc --noEmit`: clean
- Auth API test (`tests/test_auth_api.py`): 8/8 passed
  (login → token → protected 200 → bad token 401 → logout → revoked 401)

## Store builds (needs your accounts — I can't do this part for you)
1. `npm install -g eas-cli && eas login` (your own Expo account)
2. `eas init` inside `mobile/` (replaces the placeholder project ID)
3. `EXPO_PUBLIC_ARTHUR_API_URL=https://your-server.com eas build -p android`
   then `-p ios` — backend must be on public HTTPS.
4. Apple Developer ($99/yr) + Google Play Console ($25) enrollments are
   yours; then `eas submit`.

Full publishing steps: `mobile/README.md` → "Publishing to the App Store / Google Play".
