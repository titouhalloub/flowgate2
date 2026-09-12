# ---------------------------------------------------------------------------
# Stage 1: Build the React frontend with Node
# ---------------------------------------------------------------------------
FROM node:22-alpine AS frontend
WORKDIR /build

# Install dependencies first (cached layer)
COPY package.json ./
RUN npm install --no-audit --no-fund

# Copy the rest of the frontend source
COPY vite.config.ts index.html tsconfig.json tsconfig.node.json server.ts ./
COPY src ./src
COPY public ./public    # ← add this

# Build the React app.  Only vite build is needed for the production
# assets; the esbuild step that bundles server.ts is not used here
# because the Python backend serves the static files instead.
RUN npx vite build

# ---------------------------------------------------------------------------
# Stage 2: Runtime — Python FastAPI serving the built React app
# ---------------------------------------------------------------------------
FROM python:3.12-slim
WORKDIR /app

# System packages: Tesseract OCR (pytesseract backend), libGL for Pillow,
# and libmagic for file type detection on uploads.
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# App code + migrations
COPY app ./app
COPY migrations ./migrations

# Built React assets from the frontend stage
COPY --from=frontend /build/dist ./dist

# Persistent data directory (Render disk mounts at /var/data)
RUN mkdir -p /var/data/uploads

EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
