from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .connectors.geocoder import geocode
from .services import build_record
from .demo import demo_record

app = FastAPI(title="Building Record V0.4", version="0.4.0")
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")

@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/health")
async def health():
    return {"status": "ok", "version": "0.4.0"}

@app.get("/api/demo")
async def demo():
    return demo_record()

@app.get("/api/record")
async def record(
    address: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lon: float | None = Query(default=None),
):
    try:
        if address:
            g = await geocode(address)
            return await build_record(g["display_name"], g["lat"], g["lon"])
        if lat is not None and lon is not None:
            return await build_record(f"{lat}, {lon}", lat, lon)
        raise HTTPException(400, "Provide an address or lat/lon.")
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(404, str(e))
    except Exception as e:
        raise HTTPException(502, f"A public-data source could not be reached: {type(e).__name__}")
