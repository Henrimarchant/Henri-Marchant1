"""Overture building connector.

Disabled until it is moved to a safe indexed/out-of-process architecture.
Keep this module free of native Overture/PyArrow imports so merely importing
the web application cannot load or crash those dependencies.
"""

async def resolve_building(lat: float, lon: float) -> dict | None:
    return None
