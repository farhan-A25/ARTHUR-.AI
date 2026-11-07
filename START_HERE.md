# ARTHUR — Full App (START HERE)

**Owner:** Mohammed Abdul Farhan

## Run the whole app with one command

**Mac / Linux:**
```bash
bash start-arthur.sh
```

**Windows:** double-click `start-arthur.bat`

That's it. This starts:
- 🖥️ **Dashboard** → http://localhost:8000 (status, projects, agents, tasks, approvals, logs, chat)
- 💬 **ARTHUR console** → type goals like `build a markdown notes CLI`
- ⚙️ **24/7 worker** → runs in the background, executing tasks with retries and checkpoints

Type `/quit` in the console to stop everything.

## What's inside this package

| Folder / File | What it is |
|---|---|
| `backend/` | ARTHUR brain: Manager, Researcher, Developer, QA agents, task queue, tools, memory, security |
| `frontend/dashboard.html` | Futuristic web dashboard |
| `mobile/` | iOS + Android app source (Expo + React Native) |
| `mobile/assets/icon.png` | Official app logo |
| `APP_DOSSIER.md` | Ownership & product dossier (proof of creation) |
| `PRIVACY_POLICY.md` | Store-ready privacy policy |
| `docker-compose.yml` | One-command server deploy (`docker compose up`) |
| `requirements.txt` | Python dependencies |

## Phone app (iOS / Android)

```bash
cd mobile
npm install
npx expo start
```
Scan the QR code with the **Expo Go** app on your phone (same Wi-Fi).

To publish to the Play Store / App Store, follow `mobile/README.md`
(needs your Apple Developer + Google Play accounts and a hosted backend).

## Notes

- Runs in `DEMO_MODE` by default — no API keys needed. Set `DEMO_MODE=false` and add your
  `ARTHUR_LLM_*` variables (see `.env.example`) to use a real LLM.
- You are the sole Owner/Admin. First run asks you to confirm the owner name.
- Your data stays in `data/arthur.db` on your own machine.
