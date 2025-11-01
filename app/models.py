from datetime import datetime
from typing import Optional

from sqlmodel import JSON, Column, Field, SQLModel


class Product(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    artnr: Optional[str] = Field(index=True)
    category: Optional[str] = None
    name: Optional[str] = Field(default=None, max_length=1024)
    manufacturer: Optional[str] = None
    model: Optional[str] = None
    ean: Optional[str] = Field(default=None, index=True)
    stock: Optional[int] = None
    price: Optional[float] = None
    campaign: Optional[int] = None
    shipping: Optional[float] = None
    url: Optional[str] = None
    image_url: Optional[str] = None
    description_html: Optional[str] = None
    missing_price: bool = False
    missing_identifier: bool = False
    broken_image: bool = False
    improved_title: Optional[str] = None
    ai_prompt: Optional[str] = None
    raw: Optional[dict] = Field(default=None, sa_column=Column(JSON))
    created_at: datetime = Field(default_factory=datetime.utcnow)
    updated_at: datetime = Field(default_factory=datetime.utcnow)
