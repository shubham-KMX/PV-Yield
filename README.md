# PV-Yield

Address-to-rupees rooftop solar analysis for Indian homes.

Enter an address, mark your rooftop on the satellite image, and get a real
solar feasibility report: measured roof area, how many panels fit, annual
generation, savings, subsidy, and payback period. Every number comes from a
measurement or an industry-standard physics model, not a guess.

---

## What it does

The pipeline turns a street address into a complete solar report:

```
address
  -> geocode                coordinates (Google Geocoding)
  -> satellite image        rooftop imagery + meters-per-pixel (Google Static Maps)
  -> roof segmentation      pixel-accurate roof mask (MobileSAM)
  -> footprint clip         bound the roof to the real building (OpenStreetMap)
  -> shading analysis       remove obstacles and heavily shaded areas
  -> panel layout           how many panels fit -> system size in kW
  -> weather                a typical year of hourly irradiance (PVGIS)
  -> PVWatts simulation      annual + monthly generation (pvlib / NREL PVWatts)
  -> financial model        subsidy, savings, payback (India market)
  -> report                 verdict + metrics + monthly chart + PDF export
```

The core principle is measurement, not prediction. Roof area is a real
pixel count times a known meters-per-pixel factor; generation is a full
8760-hour physics simulation over real satellite weather.

---

## Architecture

The project is split into two independent applications that talk over HTTP.

```
PV-Yield/
├── backend/          FastAPI service - all the analysis logic
│   ├── app/
│   │   ├── main.py               API app + endpoints (/geocode, /satellite, /segment, /analyze)
│   │   ├── config.py             typed settings loaded from environment / .env
│   │   └── services/
│   │       ├── geocoding.py      address -> coordinates
│   │       ├── imagery.py        coordinates -> satellite image
│   │       ├── geometry.py       Web Mercator meters-per-pixel math
│   │       ├── sam_model.py      MobileSAM model loader (cached)
│   │       ├── segmentation.py   roof segmentation (points / polygon / auto)
│   │       ├── footprints.py     OSM building footprint + azimuth estimation
│   │       ├── shading.py        obstacle detection + sun-path shading
│   │       ├── weather.py        PVGIS (default) / NASA POWER weather
│   │       ├── pvwatts.py        PVWatts v5 generation simulation (pvlib)
│   │       ├── pipeline.py       end-to-end orchestrator
│   │       └── finance/          India financial model + market config
│   ├── sample_data/images/       sample satellite images for offline mode
│   ├── requirements.txt
│   └── Dockerfile
│
└── frontend/         Next.js (App Router) + Tailwind - the user interface
    ├── app/
    │   ├── page.tsx              home page (search -> select roof -> results)
    │   └── components/           Hero, RoofSelector, Results, MonthlyChart, ...
    └── lib/                      typed API client
```

- Backend: Python 3.11, FastAPI, PyTorch (CPU) + MobileSAM, pvlib, OpenCV.
- Frontend: Next.js, TypeScript, Tailwind CSS, Recharts, Framer Motion.

---

## Data sources

| Source | Used for | Key required |
|--------|----------|--------------|
| Google Geocoding API | address -> coordinates | Yes |
| Google Maps Static API | satellite imagery | Yes (same key) |
| MobileSAM | roof segmentation model (~40 MB, auto-downloaded) | No |
| OpenStreetMap (Overpass) | building footprint + orientation | No |
| PVGIS (EU JRC) | typical-year hourly irradiance and temperature | No |
| NASA POWER | alternative weather source | No |
| pvlib / NREL PVWatts | generation physics (runs locally) | No |

Only a single Google Maps API key is required, with the Geocoding API and
Maps Static API enabled, and billing active on the Google Cloud project.

---

## Prerequisites

- Python 3.11
- Node.js 18+ (Node 20+ recommended)
- A Google Maps API key with Geocoding + Static Maps enabled and billing active

---

## Setup

### 1. Clone

```bash
git clone https://github.com/shubham-KMX/PV-Yield.git
cd PV-Yield
```

### 2. Backend

```bash
cd backend

# create and activate a virtual environment
python -m venv .venv
# Windows (PowerShell):
.\.venv\Scripts\Activate.ps1
# macOS / Linux:
# source .venv/bin/activate

# install dependencies (PyTorch CPU build + CV + physics libs)
pip install -r requirements.txt
```

Create `backend/.env` (see `backend/.env.example`):

```env
GOOGLE_MAPS_API_KEY=your_google_maps_key
USE_MOCK_GEOCODING=false
USE_MOCK_IMAGERY=false
USE_MOCK_WEATHER=false
```

Run the backend:

```bash
uvicorn app.main:app --reload --port 8000
```

- API root: http://localhost:8000
- Interactive API docs: http://localhost:8000/docs

The first roof analysis downloads the MobileSAM weights (~40 MB) and loads
the model into memory, so the first request takes noticeably longer than
later ones.

### 3. Frontend

In a second terminal:

```bash
cd frontend
npm install
```

Create `frontend/.env.local` (see `frontend/.env.example`):

```env
NEXT_PUBLIC_API_URL=http://localhost:8000
```

Run the frontend:

```bash
npm run dev
```

Open http://localhost:3000.

Both servers must be running: the frontend on port 3000 calls the backend
on port 8000.

---

## Offline / mock mode

For development without hitting the paid Google APIs, set the mock toggles
in `backend/.env`:

```env
USE_MOCK_GEOCODING=true
USE_MOCK_IMAGERY=true
```

Geocoding then returns canned coordinates for a few known addresses, and
imagery is served from `backend/sample_data/images/`. Weather (PVGIS) and the
physics run for real, since they need no key. This lets the full pipeline
run end to end offline.

---

## API endpoints

| Method | Path | Purpose |
|--------|------|---------|
| GET | `/` | Health check |
| GET | `/geocode?address=...` | Address to coordinates |
| GET | `/satellite?lat=..&lng=..` | Satellite image (PNG) |
| POST | `/segment` | Measure roof area (points / polygon / auto) |
| POST | `/analyze` | Full pipeline: address to complete report |

`/analyze` accepts a JSON body with either `address` or `lat`/`lng`, an
optional roof selection (`points` or `polygon`), and optional
`monthly_consumption_kwh`, `state`, `tilt`, and `azimuth`.

---

## Configuration

Backend settings live in `backend/app/config.py` and can be overridden by
environment variables (or `backend/.env`):

- `GOOGLE_MAPS_API_KEY` - the Google Maps key (required for live mode)
- `WEATHER_SOURCE` - `pvgis` (default) or `nasa`
- `CORS_ORIGINS` - comma-separated allowed frontend origins
- `USE_MOCK_GEOCODING`, `USE_MOCK_IMAGERY`, `USE_MOCK_WEATHER` - offline toggles

The India financial model (subsidy slabs, DISCOM tariffs, net-metering
rules, loan products) lives in `backend/app/services/finance/market_config.py`.
Each entry records its source and a last-verified date.

---

## Deployment

The two apps deploy separately:

- Frontend to Vercel (root directory `frontend`, set `NEXT_PUBLIC_API_URL`
  to the deployed backend URL).
- Backend as a Docker container (`backend/Dockerfile`). Because it loads
  PyTorch and the MobileSAM model, it needs a host with roughly 1-2 GB of
  memory; a 512 MB free tier is not enough for the segmentation step.

After deploying the frontend, set `CORS_ORIGINS` on the backend to the
frontend's URL.

---

## Accuracy notes

- Generation uses PVGIS typical-meteorological-year irradiance, which is
  more representative for India than a single calendar year.
- Roof area is clipped to the OpenStreetMap building footprint where one is
  available, so segmentation does not spill onto neighbouring buildings.
- Panel azimuth is estimated from the building footprint's orientation;
  tilt defaults to the site latitude and can be overridden by the user.
- All results are pre-feasibility estimates. Confirm with a certified
  installer before making a purchase decision.

---

## License

MIT
