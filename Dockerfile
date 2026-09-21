# Bean & Bloom - single container image (frontend static files + Flask API)
FROM python:3.12-slim

WORKDIR /app

# Install backend dependencies
COPY backend/requirements.txt ./backend/requirements.txt
RUN pip install --no-cache-dir -r backend/requirements.txt

# Copy backend and frontend
COPY backend ./backend
COPY frontend ./frontend

# Vendor React/ReactDOM/Babel into the image AT BUILD TIME (your build machine needs
# internet for this step), so the running container itself needs NO outbound internet
# access at all. This is what avoids a blank page on servers with restricted egress
# (locked-down VMs, private clusters, firewalled hosts, etc.) - the browser loads
# these three files from your own server instead of a CDN.
ADD https://unpkg.com/react@18/umd/react.production.min.js ./frontend/vendor/react.production.min.js
ADD https://unpkg.com/react-dom@18/umd/react-dom.production.min.js ./frontend/vendor/react-dom.production.min.js
ADD https://unpkg.com/@babel/standalone@7/babel.min.js ./frontend/vendor/babel.min.js

# Non-root user for security
RUN useradd -m appuser && chown -R appuser:appuser /app
USER appuser

ENV PORT=5000
EXPOSE 5000

# Gunicorn serves the Flask app in production
CMD ["gunicorn", "--chdir", "backend", "--bind", "0.0.0.0:5000", "--workers", "2", "app:app"]
