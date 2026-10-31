# Hybrid cloud demo — setup guide

One small container, run in two places:

- **Mini PC (Docker/Podman)** = the retailer's *store back-room server* (on-premises)
- **Red Hat Developer Sandbox (OpenShift)** = the *public cloud*

Total setup time: about 30–45 minutes.

---

## Step 1 — Put the code on GitHub (5 min)

1. Create a new **public** GitHub repo, e.g. `hybrid-demo`.
2. Upload `app.py` and `Dockerfile` to the root of the repo.

The Developer Sandbox will build the app straight from this repo.

## Step 2 — Run it on the mini PC (5 min)

Copy `app.py` and `Dockerfile` to the mini PC (or `git clone` your repo), then in that folder:

```bash
docker build -t hybrid-demo .
docker run -d --name store --restart unless-stopped -p 8080:8080 \
  -e STORE_NAME="Maple & Co." \
  -e LOCATION="Store #214 back room" \
  -e LOCATION_TYPE=edge \
  hybrid-demo
```

Using Podman? Replace `docker` with `podman` — the commands are the same.

Open `http://<mini-pc-ip>:8080` from your laptop. You should see an **amber** banner.

## Step 3 — Run it in the public cloud (15 min)

1. Sign up at https://developers.redhat.com/developer-sandbox (free, needs a Red Hat account and phone verification; lasts 30 days).
2. Open the OpenShift console. Switch to the **Developer** view if asked.
3. Click **+Add → Import from Git** and paste your GitHub repo URL.
4. It should detect the **Dockerfile**. Make sure:
   - Target port is **8080**
   - **Create a route** is ticked (this gives you a public URL)
5. Expand **Deployment / Environment variables** and add:
   - `STORE_NAME` = `Maple & Co.`
   - `LOCATION` = `Public cloud (Red Hat OpenShift)`
   - `LOCATION_TYPE` = `cloud`
6. Click **Create**. The build takes a few minutes.
7. In **Topology**, click the arrow icon on the app to open its URL. You should see a **blue** banner.

## Step 4 — Rehearse the "Black Friday" moment

In **Topology**, click the app circle → **Details** tab → use the **up arrow** next to the pod count
to scale from 1 to 5+. The ring fills in as new copies start. Scale back to 1 afterwards.

CFO line: *"You rent extra capacity for the busy weekend instead of owning it all year."*

Refresh the cloud store page a few times: the "served by copy" name can change as different copies answer.

## Demo-day checklist

- [ ] Both browser tabs open and logged in before you start (store page on mini PC, store page in cloud, Topology view)
- [ ] Sandbox still active (30-day limit) and the app is running — Sandbox may idle apps, so open it ~15 min before
- [ ] Screen recording of the full demo saved as a backup
- [ ] Demo is ≤ 90 seconds

## Troubleshooting

- **Build fails in the Sandbox:** check the repo is public and `Dockerfile` is in the root.
- **Page won't load on mini PC:** check the firewall allows port 8080 (`sudo ufw allow 8080` on Ubuntu).
- **Change a setting on the mini PC:** `docker rm -f store`, then re-run the `docker run` command.
