# Insights Hub UI

Angular 17 UI for Insights Hub (workspaces, jobs, recommendations, chat).

## Prerequisites

- Node.js 18+
- npm

## Setup

```bash
cd UI
npm install
```

## Development

Run the API backend (from project root):

```bash
make up
# or: uvicorn API.src.main:app --reload --port 8000
```

Run the Angular dev server (from `UI` folder):

```bash
npm start
```

The app will be at **http://localhost:4200**. API requests are proxied to **http://localhost:8000** (see `proxy.conf.json`).

## Build

```bash
npm run build
```

Output is in `dist/cluster-advisor-ui/`. Serve with any static server or point your backend to this folder. (Project internal name remains cluster-advisor-ui; the app title is "Insights Hub".)

## Auth

Login is **stub-only**: any username and password (min 4 chars) will sign you in. Replace with a real auth backend when ready.

## Routes

- `/login` – Sign in
- `/app/workspaces` – List workspaces (from metrics source)
- `/app/jobs?workspaceId=...` – List jobs for a workspace
- `/app/jobs/:workspaceId/:jobId` – Job details, metrics, run recommendation, history
- `/app/chat` – Chat over job metrics (optional workspace/job scope)
- `/app/agents` – List of agents and how to use them
