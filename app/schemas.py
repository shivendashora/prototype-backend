from typing import Literal

from pydantic import BaseModel, EmailStr, Field

Category = Literal["vet_clinic", "hospital", "boarding", "diagnostics", "ambulance", "ngo"]


class Provider(BaseModel):
    id: str
    name: str
    category: Category
    city: str
    area: str
    address: str
    rating: float
    reviews: int
    pets: list[str]
    services: list[str]
    open_24x7: bool
    emergency: bool
    home_visit: bool
    verified: bool
    price_from: int | None = None
    hours: str
    phone: str
    distance_km: float
    languages: list[str] = []
    accent: str = "#0F766E"


class ProviderPage(BaseModel):
    total: int
    items: list[Provider]


class ListingIn(BaseModel):
    business_name: str = Field(min_length=2, max_length=120)
    category: Category
    city: str = Field(min_length=2, max_length=60)
    contact_name: str = Field(min_length=2, max_length=80)
    phone: str = Field(pattern=r"^[0-9+\-\s]{8,16}$")
    email: EmailStr | None = None
    services: str | None = Field(default=None, max_length=500)


class CorrectionIn(BaseModel):
    provider_id: str
    field: Literal["phone", "address", "hours", "services", "closed_permanently", "other"]
    details: str = Field(min_length=3, max_length=1000)
    reporter_email: EmailStr | None = None


class LeadIn(BaseModel):
    course_id: str | None = None
    kind: Literal["register", "enquiry", "brochure", "callback"]
    name: str = Field(min_length=2, max_length=80)
    email: EmailStr
    phone: str = Field(pattern=r"^[0-9+\-\s]{8,16}$")
    status: Literal["student", "working", "graduate", "other"] | None = None
    message: str | None = Field(default=None, max_length=1000)
    utm_source: str | None = None


class Ack(BaseModel):
    ok: bool = True
    id: int
    message: str


class CarouselRequest(BaseModel):
    idea: str = Field(min_length=5, max_length=2000)
    platform: Literal["instagram", "linkedin"] = "linkedin"
    slides: int = Field(default=7, ge=4, le=10)
    tone: Literal["educational", "bold", "friendly", "professional"] = "educational"
    brand: str = Field(default="Practo for Animals", max_length=60)


class Slide(BaseModel):
    kind: Literal["cover", "content", "stat", "quote", "cta"]
    eyebrow: str
    headline: str
    body: str
    visual_hint: str


class VisualDirection(BaseModel):
    palette: list[str]
    heading_font: str
    body_font: str
    layout: str
    imagery: str


class Carousel(BaseModel):
    title: str
    hook_options: list[str]
    caption: str
    hashtags: list[str]
    slides: list[Slide]
    visual: VisualDirection
    research_notes: list[str]
    source: Literal["claude", "template"] = "template"
