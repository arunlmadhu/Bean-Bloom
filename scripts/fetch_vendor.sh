#!/usr/bin/env bash
# Downloads React/ReactDOM/Babel into frontend/vendor/ for people running the backend
# directly (python app.py) instead of via Docker. Needs internet access ONCE, when you
# run this script - the resulting files are then served locally with no further calls out.
set -e
cd "$(dirname "$0")/.."
mkdir -p frontend/vendor
curl -fsSL -o frontend/vendor/react.production.min.js https://unpkg.com/react@18/umd/react.production.min.js
curl -fsSL -o frontend/vendor/react-dom.production.min.js https://unpkg.com/react-dom@18/umd/react-dom.production.min.js
curl -fsSL -o frontend/vendor/babel.min.js https://unpkg.com/@babel/standalone@7/babel.min.js
echo "Vendor files downloaded into frontend/vendor/"
