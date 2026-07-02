# Deploying AISync (100% free)

AISync runs on **Streamlit Community Cloud** — free, no card needed.
Everything else (auth, database) is built in with the Python standard library
and SQLite, so there are no paid services to sign up for.

## Steps

1. Push this repo to GitHub.
2. Go to https://share.streamlit.io and sign in with GitHub (free).
3. Click **New app** → pick this repo → branch `main` → main file `app.py`.
4. Click **Deploy**. First boot installs `requirements.txt` and takes a minute.
5. Share the resulting `https://<you>.streamlit.app` link.

It runs immediately with no config. **But** for real plant data, add the free
Turso database (below) — otherwise data is wiped whenever the free host
restarts.

## Accounts & data

- Each site creates a **plant workspace** (username + password). Every
  workspace's spares, consumption and stock are scoped to that workspace —
  row-level multi-tenancy, so one deployment can serve several plants.
- Passwords are hashed (pbkdf2-sha256, 200k rounds, per-user salt). Plaintext
  passwords are never stored.
- A login survives browser refreshes for 30 days via a session token.

## IMPORTANT — make data survive restarts (free, no card)

Both Streamlit Community Cloud and Render's free plan have an **ephemeral
filesystem**: when the app sleeps or redeploys, any local database file is
**wiped**. The fix is a free **hosted** database. AISync supports **Turso**
(hosted SQLite/libSQL) out of the box — same SQLite we already use, just
durable. Writes are batched into single HTTP pipelines, so the remote DB adds
minimal latency.

### Set up Turso (one time, ~3 minutes, no payment)

1. Go to https://turso.tech and sign up with GitHub (free, no card).
2. Create a database (any name, e.g. `aisync`).
3. Copy two things it gives you:
   - the **database URL** (looks like `libsql://aisync-you.turso.io`)
   - an **auth token** (generate one in the database's settings)
4. In your host's **Environment** settings, add:

```
TURSO_DATABASE_URL = libsql://aisync-you.turso.io
TURSO_AUTH_TOKEN   = <the token>
```

With those set, every workspace's data survives restarts, redeploys and
sleeps. Leave them unset and the app falls back to a local file (fine for a
demo, wiped on restart).

---

## Custom domain (optional)

Streamlit Community Cloud **cannot** use a custom domain. To hand out
something like `aisync.in`, deploy on **Render** instead — it allows custom
domains for free.

### 1. Deploy on Render (free)

1. Push this repo to GitHub.
2. https://render.com → sign up free → **New → Blueprint** → pick this repo.
   It reads `render.yaml` automatically. Click **Apply**.
3. You get `https://aisync.onrender.com` once it builds.

### 2. Attach your domain

1. Buy a domain (Cloudflare Registrar / Hostinger; `.in` ~₹500–700/yr).
2. Render dashboard → your service → **Settings → Custom Domains → Add**.
3. Add the DNS record Render shows you at your registrar. HTTPS is automatic.

### Cost summary

- Domain: ~₹99–700/yr (the only required cost, and only if you want one)
- Hosting: free on Render's free plan (sleeps when idle)
- Database: free on Turso — set the two env vars so data persists

> Note: buying the domain and editing its DNS must be done by you — those need
> your account and payment. Everything else is already wired up in this repo.
