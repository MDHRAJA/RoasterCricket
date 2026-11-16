# Vercel frontend deployment

Import `MDHRAJA/RoasterCricket` into Vercel with these settings:

| Setting | Value |
| --- | --- |
| Root Directory | `frontend` |
| Framework Preset | Vite |
| Node.js Version | 24.x |
| Install Command | `npm ci` |
| Build Command | `npm run build` |
| Output Directory | `dist` |

`frontend/vercel.json` retains the build settings. `frontend/package.json` pins the tested Node major. The application uses hash routes (`/#/fixtures`, `/#/lab`, `/#/record`), so no catch-all rewrite is needed. Builds need no Python environment or local SQLite database. The saved public frontend extracts, reviewed research artifacts, source code, tests and font-license notices are included in Git; local raw downloads, database files, environments and caches are excluded. Exact source/artifact bytes are preserved with `.gitattributes` because research receipts verify SHA-256 hashes.

## Initial frontend-only deployment

Leave `VITE_API_BASE_URL` unset. The interface displays explicitly labelled saved archive/scenario/optimizer examples and research evidence. New simulation/optimization requests require a reachable backend; hosting this static build does not start FastAPI. The existing failure messages retain prior results instead of inventing a new prediction.

## Connect live computation later

Host the existing Python service and its restored local data pack on an appropriate Python host. This repository intentionally does not redistribute the raw third-party pack or SQLite databases. Follow the source/rebuild instructions under `outputs/ipl-data/README.md` and `docs/backend.md`.

Set `VITE_API_BASE_URL` in Vercel to the backend's HTTPS API prefix, including `/api/v1`, and redeploy. This value is embedded at build time and must contain no credentials. Set the backend's `IPL_CORS_ORIGINS` to the actual frontend origin; do not allow every origin by default. Keep expensive computation bounds, availability assumptions and the experimental model labels in place.

For the local development proxy, the API remains `http://127.0.0.1:8000`. Do not use a loopback URL as a hosted frontend's API address.

Official setup references: [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite), [build and Root Directory settings](https://vercel.com/docs/builds/configure-a-build), [supported Node versions and package overrides](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
