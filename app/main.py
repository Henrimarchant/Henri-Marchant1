from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .connectors.geocoder import geocode
from .services import build_record
from .demo import demo_record


app = FastAPI(
    title="Building Record V0.5",
    version="0.5.0",
)

app.mount(
    "/static",
    StaticFiles(directory="app/static"),
    name="static",
)

templates = Jinja2Templates(directory="app/templates")


@app.get("/", response_class=HTMLResponse)
async def home(request: Request):
    return templates.TemplateResponse(
        "index.html",
        {"request": request},
    )


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.5.0",
    }


@app.get("/api/demo")
async def demo():
    return demo_record()


@app.get("/api/address-search")
async def address_search(
    address: str = Query(
        ...,
        min_length=2,
        description="Address or postcode to resolve.",
    ),
):
    """
    V0.5 property-search endpoint.

    For now this retains the existing prototype geocoder.
    It is deliberately separated from record generation so that
    authoritative UPRN resolution can be added without changing
    the Building Record API.
    """

    try:
        result = await geocode(address)

        return {
            "query": address,
            "results": [
                {
                    "display_name": result["display_name"],
                    "latitude": result["lat"],
                    "longitude": result["lon"],
                    "uprn": None,
                    "uprn_status": "unknown",
                    "uprn_confidence": None,
                    "identity_note": (
                        "Location resolved. Authoritative UPRN "
                        "has not yet been matched."
                    ),
                }
            ],
        }

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "The address-resolution source could not be reached: "
                f"{type(exc).__name__}"
            ),
        )


@app.get("/api/record")
async def record(
    address: str | None = Query(default=None),
    lat: float | None = Query(default=None),
    lon: float | None = Query(default=None),
    uprn: str | None = Query(default=None),
):
    """
    Build an evidence-backed Building Record.

    V0.5 supports UPRN throughout the record architecture while
    preserving the existing address and coordinate fallbacks.
    """

    try:
        if address:
            geocoded = await geocode(address)

            return await build_record(
                address=geocoded["display_name"],
                lat=geocoded["lat"],
                lon=geocoded["lon"],
                uprn=uprn,
            )

        if lat is not None and lon is not None:
            return await build_record(
                address=f"{lat}, {lon}",
                lat=lat,
                lon=lon,
                uprn=uprn,
            )

        raise HTTPException(
            status_code=400,
            detail="Provide an address or lat/lon.",
        )

    except HTTPException:
        raise

    except ValueError as exc:
        raise HTTPException(
            status_code=404,
            detail=str(exc),
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "A public-data source could not be reached: "
                f"{type(exc).__name__}"
            ),
        )
