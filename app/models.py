from datetime import datetime
from typing import Optional
from sqlmodel import SQLModel, Field

class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)

    artnr: Optional[str] = Field(default=None, index=True)
    category: Optional[str] = None
    name: Optional[str] = None
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    ean: Optional[str] = Field(default=None, index=True)
    stock: Optional[int] = None
    price: Optional[float] = None
    shipping: Optional[float] = None
    url: Optional[str] = None
    image_url: Optional[str] = None

    # New auto-created validation columns
    ean_status: Optional[str] = None
    price_status: Optional[str] = None
    image_status: Optional[str] = None
    validation_result: Optional[str] = None

    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
