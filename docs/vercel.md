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

The Python service can run as a second Vercel project. This repository intentionally does not redistribute the raw third-party pack or SQLite databases. Follow the source/rebuild instructions under `outputs/ipl-data/README.md` and `docs/backend.md`.

Set `VITE_API_BASE_URL` in Vercel to the backend's HTTPS API prefix, including `/api/v1`, and redeploy. This value is embedded at build time and must contain no credentials. Set the backend's `IPL_CORS_ORIGINS` to the actual frontend origin; do not allow every origin by default. Keep expensive computation bounds, availability assumptions and the experimental model labels in place.

For the local development proxy, the API remains `http://127.0.0.1:8000`. Do not use a loopback URL as a hosted frontend's API address.

## Python backend on Vercel

Use a separate project named `roaster-cricket-api`, with FastAPI and Python 3.12. The repository-root `pyproject.toml` identifies `backend.main:app`; `requirements.txt` uses the tested runtime pins. The root `vercel.json` configures a 120-second maximum request duration and the Mumbai region. The frontend keeps its independent `frontend/vercel.json` configuration.

The backend requires the local SQLite snapshot. Importing only the Git repository cannot supply it. Prepare a clean upload directory from the validated local pack:

```powershell
python scripts/stage_vercel_backend.py
npx --yes vercel@65.16.0 --cwd work/vercel/backend --scope mdh6 deploy --project roaster-cricket-api --prod --archive=tgz
```

Run these from the repository root using the project's Python environment. Sign into Vercel CLI in your own browser if required. For a later deployment, choose a fresh output directory with `--output work/vercel/backend-next` and pass that directory to the CLI. Existing deployment directories are never cleared or replaced by the packaging script.

The exporter uses an explicit file allowlist: backend Python files, deployment configuration/checker, runtime dependencies, the database, catalog, coverage summary and optional availability CSV. Raw downloads, processed CSV exports, research reports, local environments, credentials and the entire frontend are excluded. The database stays inside the function bundle; no static route or raw-download endpoint is created. Keep Vercel source visibility private. Source attribution and the restrictions in `outputs/ipl-data/README.md` still apply.

Use `--archive=tgz`: the database exceeds Hobby's 100 MB source-upload limit. Vercel's supported archive upload compresses the source before transmission. This does not alter the database bytes or increase the function bundle allowance. The build checks immutable runtime files' sizes and SHA-256 hashes, validates the catalog/schema, runs SQLite's integrity check and verifies read-only access. Platform-normalized configuration is excluded from those receipts. Missing or changed runtime files stop the build.

Set these backend environment variables:

| Variable | Value |
| --- | --- |
| `IPL_DATA_DIR` | `outputs/ipl-data` |
| `IPL_CORS_ORIGINS` | `https://roaster-cricket.vercel.app` (use the actual frontend origin) |
| `OPENBLAS_NUM_THREADS` | `1` |
| `OMP_NUM_THREADS` | `1` |

Once the backend is ready, set the frontend's `VITE_API_BASE_URL` to its HTTPS URL followed by `/api/v1`, then redeploy the frontend. Do not put credentials or protection-bypass tokens in this public build variable.

Check `/health`, `/ready`, metadata, CORS preflight, simulation and optimization after deployment. Verify that `/outputs/ipl-data/ipl.sqlite` returns 404. Local request timings do not establish hosted performance. Computation limits and the experimental forecast labels remain in place. The existing planning slot applies per process, not across Vercel's independently scaled instances. Dataset updates require a new checked backend deployment; runtime requests never modify the database. Historical research/backtesting remains offline.

Official setup references: [Vite on Vercel](https://vercel.com/docs/frameworks/frontend/vite), [FastAPI on Vercel](https://vercel.com/docs/frameworks/backend/fastapi), [archive uploads](https://vercel.com/docs/cli/deploy#archive), [function limits](https://vercel.com/docs/functions/limitations), [build and Root Directory settings](https://vercel.com/docs/builds/configure-a-build), [supported Node versions and package overrides](https://vercel.com/docs/functions/runtimes/node-js/node-js-versions).
