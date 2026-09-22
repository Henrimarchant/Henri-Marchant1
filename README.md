# Building Record V0

Evidence-backed digital building records.

## What V0 proves
Enter an England address (or latitude/longitude), resolve a location, retrieve public planning/constraint evidence, and build a structured Building Record where every fact carries provenance and status.

## Evidence statuses
- `recorded` — returned by an identified source
- `estimated` — derived/inferred and clearly labelled
- `verified` — reserved for later professional/document verification
- `unknown` — not evidenced

## Run locally
```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload
```

Open http://127.0.0.1:8000

## V0 connectors
- OpenStreetMap Nominatim: prototype address geocoding only
- Planning Data for England: public planning/constraint evidence
- Overture Maps: connector contract prepared; building/GERS resolver is the next integration

Production will replace prototype geocoding with a licensed/appropriate address-resolution service and add a data-rights registry for every source.

## V0.2 milestone
The resolver now queries Overture buildings in a small bounding box around the geocoded point, prefers a footprint containing that point, assigns the returned building feature/GERS identifier where present, and imports available building/roof attributes as sourced facts. Missing fields remain explicitly unknown.

Note: Overture's current schema documentation is v2.0.0 while the latest published data release at 22 Sep 2026 remains 2026-08-19.0 (schema v1.18.0). The connector only relies on fields documented in the building model and does not hard-code the next data release.

## V0.3 milestone — Building History + Roof Record
- Added first-class `Component` and `Event` models.
- Every building receives a stable primary Roof Record.
- Available Overture roof evidence is inherited into the component with provenance.
- Roof installation/replacement dates, condition, inspection history, repairs and remaining service life stay `unknown` until evidenced.
- Added a planning-history evidence stream. Empty planning results are explicitly not treated as proof that a building has never been altered.
- UI now exposes Roof Record and Building History independently from general building facts.

This is intentionally conservative: V0.3 establishes the evidence architecture before adding age estimation, imagery inference or service-life predictions.

## V0.4 milestone — runnable website
V0.4 is packaged as a deployable FastAPI web application.

New:
- `/health` deployment health check.
- `/api/demo` self-contained synthetic demonstration Building Record.
- Live address search remains available through `/api/record`.
- UI can render identity, facts, planning constraints, Roof Record, Building History and explicit Unknowns.
- Graceful public-source failure message rather than an application crash.
- `render.yaml` and `Procfile` added for straightforward web deployment.

### Important
The demonstration property is synthetic and is clearly labelled. It exists so the product experience can be tested without pretending that invented information belongs to a real building.

### Local launch
Install Python 3.12+, then:
`pip install -r requirements.txt`
`uvicorn app.main:app --reload`
Open `http://127.0.0.1:8000`.

### Deployment
The package is ready for a Python web host. It has not been published to a public URL from this environment; deployment requires a hosting account/project or a working repository integration.
