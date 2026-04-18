import enum
import datetime as dt
from typing import Annotated, Optional

from sqlalchemy import (
    BigInteger,
    Boolean,
    DateTime,
    Enum,
    ForeignKey,
    JSON,
    Numeric,
    String,
    Text,
    Index,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base
from app.db.mixins import TimestampMixin, CreatedAtMixin


NumericQty = Annotated[float, mapped_column(Numeric(14, 3))]
NumericMoney = Annotated[float, mapped_column(Numeric(14, 2))]


class MovementType(str, enum.Enum):
    INBOUND = "inbound"
    OUTBOUND = "outbound"
    ADJUST = "adjust"
    RESERVE = "reserve"


class SaleStatus(str, enum.Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    CANCELLED = "cancelled"


class DocumentStatus(str, enum.Enum):
    DRAFT = "draft"
    READY = "ready"
    ERROR = "error"


class SourceType(str, enum.Enum):
    TELEGRAM_TEXT = "telegram_text"
    TELEGRAM_VOICE = "telegram_voice"
    FILE = "file"
    MANUAL = "manual"


class UserRole(str, enum.Enum):
    ADMIN = "admin"
    MANAGER = "manager"
    VIEWER = "viewer"


class Product(TimestampMixin, Base):
    __tablename__ = "products"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sku: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    brand: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    category: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    price: Mapped[Optional[NumericMoney]] = mapped_column(nullable=True)
    currency: Mapped[Optional[str]] = mapped_column(String(3), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    attributes_json: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    inventory: Mapped["Inventory"] = relationship(
        back_populates="product", uselist=False, cascade="all, delete-orphan"
    )
    stock_movements: Mapped[list["StockMovement"]] = relationship(
        back_populates="product", cascade="all, delete-orphan"
    )
    sale_items: Mapped[list["SaleItem"]] = relationship(back_populates="product")

    __table_args__ = (
        Index("ix_products_name", "name"),
        Index("ix_products_category", "category"),
        Index("ix_products_brand", "brand"),
    )


class Inventory(Base):
    __tablename__ = "inventory"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), unique=True, nullable=False
    )
    stock_doc: Mapped[NumericQty] = mapped_column(default=0, nullable=False)
    stock_fact: Mapped[NumericQty] = mapped_column(default=0, nullable=False)
    reserved_qty: Mapped[NumericQty] = mapped_column(default=0, nullable=False)
    updated_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), default=dt.datetime.utcnow, onupdate=dt.datetime.utcnow, nullable=False
    )

    product: Mapped[Product] = relationship(back_populates="inventory")


class StockMovement(CreatedAtMixin, Base):
    __tablename__ = "stock_movements"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    product_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="CASCADE"), nullable=False
    )
    movement_type: Mapped[MovementType] = mapped_column(Enum(MovementType), nullable=False)
    quantity: Mapped[NumericQty] = mapped_column(nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    source: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    comment: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    product: Mapped[Product] = relationship(back_populates="stock_movements")
    creator: Mapped[Optional["User"]] = relationship(back_populates="stock_movements")

    __table_args__ = (
        Index("ix_stock_movements_product", "product_id"),
        Index("ix_stock_movements_type", "movement_type"),
    )


class Sale(CreatedAtMixin, Base):
    __tablename__ = "sales"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sale_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    sale_date: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    source_type: Mapped[SourceType] = mapped_column(Enum(SourceType), nullable=False)
    status: Mapped[SaleStatus] = mapped_column(Enum(SaleStatus), nullable=False)
    customer_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    total_amount: Mapped[NumericMoney] = mapped_column(nullable=False)
    currency: Mapped[str] = mapped_column(String(3), nullable=False)
    raw_input_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )

    items: Mapped[list["SaleItem"]] = relationship(
        back_populates="sale", cascade="all, delete-orphan"
    )
    documents: Mapped[list["Document"]] = relationship(back_populates="sale")
    creator: Mapped[Optional["User"]] = relationship(back_populates="sales")

    __table_args__ = (
        Index("ix_sales_sale_date", "sale_date"),
        Index("ix_sales_status", "status"),
    )


class SaleItem(Base):
    __tablename__ = "sale_items"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    sale_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("sales.id", ondelete="CASCADE"), nullable=False
    )
    product_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("products.id", ondelete="SET NULL"), nullable=True
    )
    product_name_snapshot: Mapped[str] = mapped_column(String(255), nullable=False)
    sku_snapshot: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    quantity: Mapped[NumericQty] = mapped_column(nullable=False)
    unit: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    unit_price: Mapped[NumericMoney] = mapped_column(nullable=False)
    line_total: Mapped[NumericMoney] = mapped_column(nullable=False)

    sale: Mapped[Sale] = relationship(back_populates="items")
    product: Mapped[Optional[Product]] = relationship(back_populates="sale_items")

    __table_args__ = (
        Index("ix_sale_items_sale_id", "sale_id"),
        Index("ix_sale_items_product_id", "product_id"),
    )


class Document(CreatedAtMixin, Base):
    __tablename__ = "documents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    document_type: Mapped[str] = mapped_column(String(64), nullable=False)
    related_sale_id: Mapped[Optional[int]] = mapped_column(
        BigInteger, ForeignKey("sales.id", ondelete="SET NULL"), nullable=True
    )
    document_number: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    file_path: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    status: Mapped[DocumentStatus] = mapped_column(Enum(DocumentStatus), nullable=False)

    sale: Mapped[Optional[Sale]] = relationship(back_populates="documents")

    __table_args__ = (
        Index("ix_documents_related_sale", "related_sale_id"),
        Index("ix_documents_type", "document_type"),
    )


class User(CreatedAtMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    telegram_user_id: Mapped[Optional[int]] = mapped_column(BigInteger, unique=True, nullable=True)
    username: Mapped[Optional[str]] = mapped_column(String(255), unique=True, nullable=True)
    full_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[UserRole] = mapped_column(Enum(UserRole), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    stock_movements: Mapped[list[StockMovement]] = relationship(back_populates="creator")
    sales: Mapped[list[Sale]] = relationship(back_populates="creator")

    __table_args__ = (
        Index("ix_users_role", "role"),
        Index("ix_users_is_active", "is_active"),
    )


__all__ = [
    "Product",
    "Inventory",
    "StockMovement",
    "Sale",
    "SaleItem",
    "Document",
    "User",
    "MovementType",
    "SaleStatus",
    "DocumentStatus",
    "SourceType",
    "UserRole",
]
