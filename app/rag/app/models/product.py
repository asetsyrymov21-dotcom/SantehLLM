from __future__ import annotations

from sqlalchemy import Column, Integer, String, Text

from app.db.base import Base


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, autoincrement=True)
    tenant_id = Column(String(64), nullable=True, index=True)
    sku = Column(String(64), nullable=True, index=True)
    name = Column(String(255), nullable=False)
    brand = Column(String(255), nullable=True)
    category = Column(String(255), nullable=True)
    short_description = Column(Text, nullable=True)
    description = Column(Text, nullable=True)
    attributes_json = Column(Text, nullable=True)
