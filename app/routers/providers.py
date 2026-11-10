"""Practo for Animals — provider discovery API."""
from typing import Literal

from fastapi import APIRouter, HTTPException, Query

from ..db import SessionDep
from ..data import load
from ..models import Correction, Listing
from ..schemas import Ack, CorrectionIn, ListingIn, Provider, ProviderPage

router = APIRouter(prefix="/api/pets", tags=["Practo for Animals"])

CATEGORIES = [
    {"id": "vet_clinic", "label": "Vet Clinics", "icon": "stethoscope"},
    {"id": "hospital", "label": "Hospitals", "icon": "hospital"},
    {"id": "boarding", "label": "Boarding", "icon": "home"},
    {"id": "diagnostics", "label": "Diagnostics", "icon": "flask"},
    {"id": "ambulance", "label": "Ambulance", "icon": "siren"},
    {"id": "ngo", "label": "NGOs & Rescue", "icon": "heart"},
]
PETS = ["dog", "cat", "bird", "cattle", "exotic"]


@router.get("/meta")
async def meta():
    providers = load("providers")
    cities = sorted({p["city"] for p in providers})
    counts = {c["id"]: sum(p["category"] == c["id"] for p in providers) for c in CATEGORIES}
    return {
        "categories": [{**c, "count": counts[c["id"]]} for c in CATEGORIES],
        "cities": cities,
        "pets": PETS,
        "stats": {"providers": len(providers), "cities": len(cities), "verified": sum(p["verified"] for p in providers)},
    }


@router.get("/providers", response_model=ProviderPage)
async def search_providers(
    q: str | None = Query(None, description="Free text: name, area, service"),
    category: str | None = None,
    city: str | None = None,
    pet: str | None = None,
    open_24x7: bool = False,
    emergency: bool = False,
    home_visit: bool = False,
    verified: bool = False,
    min_rating: float = Query(0, ge=0, le=5),
    max_price: int | None = Query(None, ge=0),
    sort: Literal["relevance", "rating", "distance", "price"] = "relevance",
    limit: int = Query(50, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    items = load("providers")
    if q:
        needle = q.lower().strip()
        items = [
            p for p in items
            if needle in " ".join([p["name"], p["area"], p["city"], p["category"], *p["services"]]).lower()
        ]
    if category:
        items = [p for p in items if p["category"] == category]
    if city:
        items = [p for p in items if p["city"].lower() == city.lower()]
    if pet:
        items = [p for p in items if pet in p["pets"]]
    for flag, on in (("open_24x7", open_24x7), ("emergency", emergency), ("home_visit", home_visit), ("verified", verified)):
        if on:
            items = [p for p in items if p[flag]]
    items = [p for p in items if p["rating"] >= min_rating]
    if max_price is not None:
        items = [p for p in items if p["price_from"] is None or p["price_from"] <= max_price]

    if sort == "rating":
        items = sorted(items, key=lambda p: (-p["rating"], -p["reviews"]))
    elif sort == "distance":
        items = sorted(items, key=lambda p: p["distance_km"])
    elif sort == "price":
        items = sorted(items, key=lambda p: p["price_from"] if p["price_from"] is not None else 0)
    else:  # relevance: verified + emergency-ready first, then rating weighted by review volume
        items = sorted(items, key=lambda p: (not p["verified"], -(p["rating"] * min(p["reviews"], 2000) ** 0.25)))

    return {"total": len(items), "items": items[offset: offset + limit]}


@router.get("/providers/{provider_id}", response_model=Provider)
async def get_provider(provider_id: str):
    for p in load("providers"):
        if p["id"] == provider_id:
            return p
    raise HTTPException(404, "Provider not found")


@router.post("/listings", response_model=Ack, status_code=201)
async def list_business(body: ListingIn, session: SessionDep):
    listing = Listing(
        business_name=body.business_name, category=body.category,
        city=body.city, phone=body.phone, payload=body.model_dump(mode="json"),
    )
    session.add(listing)
    await session.commit()
    return Ack(id=listing.id, message="Thanks! Our team will verify your listing within 48 hours.")


@router.post("/corrections", response_model=Ack, status_code=201)
async def submit_correction(body: CorrectionIn, session: SessionDep):
    await get_provider(body.provider_id)  # 404 if unknown
    correction = Correction(provider_id=body.provider_id, field=body.field, payload=body.model_dump(mode="json"))
    session.add(correction)
    await session.commit()
    return Ack(id=correction.id, message="Correction received — we'll review and update the listing.")
