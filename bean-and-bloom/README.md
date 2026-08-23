# Bean & Bloom

Coffee, soft drinks and snacks ordering site. React frontend (no build step — loaded
locally with in-browser Babel, nothing to `npm install`), Python/Flask backend API,
single Docker image, Kubernetes manifests. UI runs on **port 5000**.

## What's inside

```
bean-and-bloom/
├── frontend/
│   ├── index.html         # Whole React app - Navbar, Home, Menu, Cart, Checkout,
│   │                       #   Admin Login, Admin Dashboard, 404 page, client-side router
│   └── vendor/             # React/ReactDOM/Babel, populated at build time (see below)
├── backend/
│   ├── app.py              # Flask API (menu, orders, admin login) + serves the frontend
│   ├── requirements.txt
│   └── orders.json         # Simple JSON "database" for placed orders
├── scripts/
│   └── fetch_vendor.sh     # One-time download of vendor/ files if not using Docker
├── Dockerfile               # Single-stage image, no docker-compose needed, port 5000
├── k8s/
│   ├── deployment.yaml      # Deployment + Secret (env vars for admin creds/secret key)
│   ├── service.yaml
│   └── ingress.yaml
└── README.md
```

## No hotlinked photos, on purpose

Every menu item's "image" is a small inline SVG shape (cup / glass / plate) plus a
matching emoji, generated in the browser — not a photo pulled from the internet. That
guarantees the art always matches the item (no more random unrelated stock photos),
and means the page never depends on an external image host being reachable.

## Running it locally

The frontend is a single static `index.html` — no build tools needed. The only thing
that needs Python packages is the backend, and Docker handles that for you.

**Option A — Docker (recommended, nothing to install yourself):**
```bash
docker build -t bean-and-bloom .
docker run -p 5000:5000 bean-and-bloom
```
Then open http://localhost:5000

**Option B — If you do have Python available:**
```bash
./scripts/fetch_vendor.sh   # one-time download of React/ReactDOM/Babel into frontend/vendor/
cd backend
pip install -r requirements.txt
python app.py
```

## Why this needs internet at build time, not run time

The frontend needs React, ReactDOM, and Babel (to run JSX in the browser with no
build step). The `Dockerfile` downloads those three files *at build time*
(`ADD https://unpkg.com/...`) and bakes them into the image under `frontend/vendor/`.
The page loads them from your own server (`/vendor/...`), so the **running container
needs zero outbound internet access** — only your build machine needs internet, and
only while running `docker build`.

If your Docker build machine is also fully offline, run `scripts/fetch_vendor.sh` on
any machine with internet, then copy the resulting `frontend/vendor/` folder into this
project before building.

## Admin login

Default demo credentials: `admin` / `admin123`
**Change these before any real deployment** — see "Security" below.

## Deploying to Kubernetes

1. Build and push the image to your registry:
   ```bash
   docker build -t your-registry/bean-and-bloom:latest .
   docker push your-registry/bean-and-bloom:latest
   ```
2. Update `k8s/deployment.yaml`:
   - Set `image:` to the image you pushed.
   - Replace the `Secret` values (`secret-key`, `admin-username`, `admin-password-hash`).
     Generate a real hash with:
     ```bash
     python -c "from werkzeug.security import generate_password_hash; print(generate_password_hash('your-new-password'))"
     ```
3. Update `k8s/ingress.yaml` with your real hostname and TLS secret.
4. Apply everything (all resources live in the `bean-and-bloom` namespace —
   change the `namespace:` field in each manifest, including `k8s/namespace.yaml`,
   if you want a different one):
   ```bash
   kubectl apply -f k8s/namespace.yaml
   kubectl apply -f k8s/deployment.yaml
   kubectl apply -f k8s/service.yaml
   kubectl apply -f k8s/ingress.yaml
   ```

## Security & compliance notes

- Admin password is stored as a salted hash (`werkzeug.security`), never plaintext.
- Session tokens are signed and expire after 1 hour (`itsdangerous`), not raw session IDs.
- Login returns the same generic error for a bad username or bad password (avoids
  telling attackers which one was wrong).
- All order-placing input is validated server-side (item IDs checked against the real
  menu, quantities bounds-checked) — the server never trusts client-supplied prices.
- The container runs as a non-root user.
- Swap `orders.json` for a real database (Postgres, etc.) before production use — the
  JSON file is fine for a demo but isn't safe for concurrent writes at scale.
- Rotate `SECRET_KEY` and admin credentials via the Kubernetes `Secret`, never commit
  real secrets to source control.

## Pages

- `/` — Home / hero
- `/menu` — Full menu with Coffee / Drinks / Snacks tabs, quantity selector, add to cart
- `/checkout` — Cart summary, place order
- `/login` — Admin login
- `/admin` — Admin dashboard (protected, lists all orders)
- Any unknown URL — custom 404 page
