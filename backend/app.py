"""
Bean & Bloom - Backend API
---------------------------
A small, dependency-light Flask backend that:
  - Serves the static React (CDN-free, vendored) frontend
  - Exposes a JSON API for the menu, cart/order placement, and admin login
  - Stores orders in a local JSON file (swap for a real DB in production)

Security notes (kept intentionally simple but production-sane):
  - Admin password is stored as a salted hash (werkzeug.security), never plaintext.
  - Admin credentials & secret key are read from environment variables with safe
    fallbacks for local/dev use only -- override these in real deployments.
  - Session tokens are signed, expiring tokens (itsdangerous), not raw session IDs.
  - All mutating endpoints validate/sanitize input and return proper HTTP codes.
  - CORS is locked down to same-origin by default (frontend is served by this app).
"""
import os
import json
import time
import uuid
from functools import wraps

from flask import Flask, request, jsonify, send_from_directory
from werkzeug.security import generate_password_hash, check_password_hash
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FRONTEND_DIR = os.path.join(os.path.dirname(BASE_DIR), "frontend")
DATA_FILE = os.path.join(BASE_DIR, "orders.json")

# ---- Configuration (override via environment variables in real deployments) ----
SECRET_KEY = os.environ.get("SECRET_KEY", "change-this-secret-in-production")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
# Default password is "admin123" -- CHANGE THIS via ADMIN_PASSWORD_HASH env var.
ADMIN_PASSWORD_HASH = os.environ.get(
    "ADMIN_PASSWORD_HASH",
    generate_password_hash(os.environ.get("ADMIN_PASSWORD", "admin123")),
)
TOKEN_MAX_AGE_SECONDS = int(os.environ.get("TOKEN_MAX_AGE_SECONDS", "3600"))

app = Flask(__name__, static_folder=None)
app.config["SECRET_KEY"] = SECRET_KEY
serializer = URLSafeTimedSerializer(SECRET_KEY)

# ---------------------------------------------------------------------------
# Menu data (in a real system this would live in a database)
# "art" describes the built-in vector/icon illustration to render for the item
# (see ProductArt in the frontend) -- no photos, no external image requests.
# ---------------------------------------------------------------------------
MENU = [
    # ---- Coffee ----
    {"id": "esp-01", "category": "coffee", "name": "Espresso",
     "description": "A bold, concentrated shot of specialty espresso.",
     "price": 3.49, "art": {"shape": "cup", "icon": "☕", "tone": "coffee"}},
    {"id": "cap-01", "category": "coffee", "name": "Cappuccino",
     "description": "Equal parts espresso, steamed milk and silky foam.",
     "price": 4.49, "art": {"shape": "cup", "icon": "☕", "tone": "coffee-light"}},
    {"id": "lat-01", "category": "coffee", "name": "Caramel Latte",
     "description": "Smooth espresso and steamed milk with a caramel swirl.",
     "price": 4.79, "art": {"shape": "cup", "icon": "🥤", "tone": "caramel"}},
    {"id": "moc-01", "category": "coffee", "name": "Black Forest Mocha",
     "description": "Chocolate-kissed coffee crowned with whipped cream.",
     "price": 5.29, "art": {"shape": "cup", "icon": "🍫", "tone": "mocha"}},
    {"id": "ice-01", "category": "coffee", "name": "Cold Brew",
     "description": "Slow-steeped, smooth and naturally sweet, served over ice.",
     "price": 4.29, "art": {"shape": "cup", "icon": "🧊", "tone": "coldbrew"}},

    # ---- Soft drinks ----
    {"id": "col-01", "category": "drinks", "name": "Classic Cola",
     "description": "Crisp, fizzy cola served ice-cold.",
     "price": 2.49, "art": {"shape": "glass", "icon": "🥤", "tone": "cola"}},
    {"id": "lem-01", "category": "drinks", "name": "Fresh Lemonade",
     "description": "Hand-squeezed lemons, lightly sweetened, served chilled.",
     "price": 2.99, "art": {"shape": "glass", "icon": "🍋", "tone": "lemon"}},
    {"id": "ort-01", "category": "drinks", "name": "Orange Soda",
     "description": "Bright, bubbly orange soda over ice.",
     "price": 2.49, "art": {"shape": "glass", "icon": "🍊", "tone": "orange"}},
    {"id": "ict-01", "category": "drinks", "name": "Iced Tea",
     "description": "Freshly brewed black tea, chilled and lightly sweetened.",
     "price": 2.79, "art": {"shape": "glass", "icon": "🍵", "tone": "tea"}},
    {"id": "spw-01", "category": "drinks", "name": "Sparkling Water",
     "description": "Crisp carbonated water with a twist of lime.",
     "price": 1.99, "art": {"shape": "glass", "icon": "💧", "tone": "sparkling"}},

    # ---- Snacks ----
    {"id": "cro-01", "category": "snacks", "name": "Butter Croissant",
     "description": "Flaky, buttery, baked fresh every morning.",
     "price": 3.29, "art": {"shape": "plate", "icon": "🥐", "tone": "pastry"}},
    {"id": "muf-01", "category": "snacks", "name": "Chocolate Muffin",
     "description": "Rich chocolate muffin studded with chocolate chips.",
     "price": 3.49, "art": {"shape": "plate", "icon": "🧁", "tone": "chocolate"}},
    {"id": "pre-01", "category": "snacks", "name": "Soft Pretzel",
     "description": "Warm, salted soft pretzel, baked to order.",
     "price": 3.99, "art": {"shape": "plate", "icon": "🥨", "tone": "pretzel"}},
    {"id": "chp-01", "category": "snacks", "name": "Sea Salt Chips",
     "description": "Crunchy kettle-cooked chips, lightly salted.",
     "price": 2.49, "art": {"shape": "plate", "icon": "🍟", "tone": "chips"}},
    {"id": "coo-01", "category": "snacks", "name": "Choc Chip Cookie",
     "description": "Classic, chewy, loaded with chocolate chips.",
     "price": 2.79, "art": {"shape": "plate", "icon": "🍪", "tone": "cookie"}},
]

# ---------------------------------------------------------------------------
# Persistence helpers (simple JSON file "database")
# ---------------------------------------------------------------------------
def _load_orders():
    if not os.path.exists(DATA_FILE):
        return []
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return []


def _save_orders(orders):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(orders, f, indent=2)


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------
def require_admin(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"error": "Missing or invalid Authorization header"}), 401
        token = auth.split(" ", 1)[1]
        try:
            data = serializer.loads(token, max_age=TOKEN_MAX_AGE_SECONDS)
        except SignatureExpired:
            return jsonify({"error": "Session expired, please log in again"}), 401
        except BadSignature:
            return jsonify({"error": "Invalid session token"}), 401
        if data.get("role") != "admin":
            return jsonify({"error": "Admin privileges required"}), 403
        return fn(*args, **kwargs)
    return wrapper


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/health")
def health():
    return jsonify({"status": "ok"})


@app.get("/api/menu")
def get_menu():
    category = request.args.get("category")
    items = MENU if not category else [m for m in MENU if m["category"] == category]
    return jsonify({"items": items})


@app.post("/api/login")
def login():
    body = request.get_json(silent=True) or {}
    username = (body.get("username") or "").strip()
    password = body.get("password") or ""

    if not username or not password:
        return jsonify({"error": "Username and password are required"}), 400

    if username != ADMIN_USERNAME or not check_password_hash(ADMIN_PASSWORD_HASH, password):
        # Same generic error whether user or password is wrong -- avoids user enumeration.
        return jsonify({"error": "Invalid credentials"}), 401

    token = serializer.dumps({"username": username, "role": "admin"})
    return jsonify({"token": token, "expiresIn": TOKEN_MAX_AGE_SECONDS})


@app.post("/api/orders")
def place_order():
    body = request.get_json(silent=True) or {}
    items = body.get("items")
    customer_name = (body.get("customerName") or "").strip()

    if not customer_name:
        return jsonify({"error": "customerName is required"}), 400
    if not isinstance(items, list) or len(items) == 0:
        return jsonify({"error": "items must be a non-empty list"}), 400

    menu_by_id = {m["id"]: m for m in MENU}
    order_items = []
    total = 0.0

    for raw in items:
        item_id = raw.get("id")
        qty = raw.get("quantity")
        if item_id not in menu_by_id:
            return jsonify({"error": f"Unknown item id: {item_id}"}), 400
        if not isinstance(qty, int) or qty < 1 or qty > 50:
            return jsonify({"error": f"Invalid quantity for {item_id}"}), 400
        menu_item = menu_by_id[item_id]
        line_total = round(menu_item["price"] * qty, 2)
        total += line_total
        order_items.append({
            "id": item_id,
            "name": menu_item["name"],
            "unitPrice": menu_item["price"],
            "quantity": qty,
            "lineTotal": line_total,
        })

    order = {
        "id": str(uuid.uuid4()),
        "customerName": customer_name,
        "items": order_items,
        "total": round(total, 2),
        "status": "received",
        "createdAt": int(time.time()),
    }

    orders = _load_orders()
    orders.append(order)
    _save_orders(orders)

    return jsonify({"order": order}), 201


@app.get("/api/admin/orders")
@require_admin
def admin_list_orders():
    orders = _load_orders()
    orders_sorted = sorted(orders, key=lambda o: o["createdAt"], reverse=True)
    return jsonify({"orders": orders_sorted})


# ---------------------------------------------------------------------------
# Static frontend (served by the same app for simple, single-container hosting)
# ---------------------------------------------------------------------------
@app.get("/")
def serve_index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/<path:path>")
def serve_static(path):
    full_path = os.path.join(FRONTEND_DIR, path)
    if os.path.isfile(full_path):
        return send_from_directory(FRONTEND_DIR, path)
    # Unknown non-API path -> let the SPA's client-side router show the 404 page.
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.errorhandler(404)
def not_found(e):
    if request.path.startswith("/api/"):
        return jsonify({"error": "Not found"}), 404
    return send_from_directory(FRONTEND_DIR, "index.html")


if __name__ == "__main__":
    # Default UI port is 5000, per deployment requirement.
    port = int(os.environ.get("PORT", "5000"))
    app.run(host="0.0.0.0", port=port)
