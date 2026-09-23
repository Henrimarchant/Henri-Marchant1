from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from .connectors.geocoder import geocode
from .services import build_record
from .connectors.open_uprn import resolve_uprn, corroborate_uprn
from .connectors.uprn_postgis import close_pool
from .models import EvidenceStatus
from .demo import demo_record


app = FastAPI(
    title="Building Record V0.6",
    version="0.6.0",
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


@app.on_event("shutdown")
async def shutdown_connections():
    await close_pool()


@app.get("/health")
async def health():
    return {
        "status": "ok",
        "version": "0.6.0",
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
    V0.6 property-search endpoint.

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
                    "identity_confirmed": result.get("identity_confirmed", False),
                    "identity_method": result.get("identity_method"),
                    "identity_note": (
                        "Location candidate validated against the supplied search. "
                        "Authoritative UPRN has not yet been matched."
                        if result.get("identity_confirmed")
                        else
                        "A location was resolved, but unique property identity is not yet confirmed."
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

    V0.6 supports UPRN throughout the record architecture while
    requiring confirmed address identity before public-data enrichment.
    """

    try:
        if address:
            geocoded = await geocode(address)

            # Hard safety gate: never enrich an address search unless identity
            # validation passed. Unknown/ambiguous identity must remain unknown.
            if not geocoded.get("identity_confirmed"):
                raise ValueError(
                    "Property identity is not confirmed. Please enter a full property address including postcode."
                )

            # Caller-supplied identifiers are never trusted. The official
            # OS Open UPRN dataset may verify the validated geocoder point.
            resolved_uprn = await resolve_uprn(geocoded["lat"], geocoded["lon"])
            resolved_uprn = await corroborate_uprn(address, resolved_uprn)
            return await build_record(
                address=geocoded["display_name"],
                lat=geocoded["lat"],
                lon=geocoded["lon"],
                uprn=resolved_uprn["uprn"] if resolved_uprn else None,
                uprn_status=resolved_uprn["status"] if resolved_uprn else EvidenceStatus.unknown,
                uprn_confidence=resolved_uprn["confidence"] if resolved_uprn else None,
                uprn_source=resolved_uprn["source"] if resolved_uprn else None,
            )

        if lat is not None and lon is not None:
            # Raw coordinates are useful internally, but they do not prove
            # which building/property the user intended. Do not attach
            # property-specific evidence to them through the public endpoint.
            raise HTTPException(
                status_code=422,
                detail=(
                    "Coordinates alone do not confirm a property identity. "
                    "Search using a full property address including postcode."
                ),
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
