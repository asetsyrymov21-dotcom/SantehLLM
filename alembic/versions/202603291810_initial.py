"""initial schema"""

from alembic import op
import sqlalchemy as sa

revision = "202603291810"
down_revision = None
branch_labels = None
depends_on = None


movement_type_enum = sa.Enum(
    "inbound", "outbound", "adjust", "reserve", name="movementtype"
)
sale_status_enum = sa.Enum("draft", "confirmed", "cancelled", name="salestatus")
document_status_enum = sa.Enum("draft", "ready", "error", name="documentstatus")
source_type_enum = sa.Enum("telegram", "manual", "import", name="sourcetype")
user_role_enum = sa.Enum("admin", "manager", "viewer", name="userrole")


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("telegram_user_id", sa.BigInteger(), nullable=True, unique=True),
        sa.Column("username", sa.String(length=255), nullable=True, unique=True),
        sa.Column("full_name", sa.String(length=255), nullable=True),
        sa.Column("role", user_role_enum, nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_users_role", "users", ["role"], unique=False)
    op.create_index("ix_users_is_active", "users", ["is_active"], unique=False)

    op.create_table(
        "products",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sku", sa.String(length=64), nullable=False, unique=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("brand", sa.String(length=255), nullable=True),
        sa.Column("category", sa.String(length=255), nullable=True),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("price", sa.Numeric(14, 2), nullable=True),
        sa.Column("currency", sa.String(length=3), nullable=True),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("attributes_json", sa.JSON(), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )
    op.create_index("ix_products_name", "products", ["name"], unique=False)
    op.create_index("ix_products_category", "products", ["category"], unique=False)
    op.create_index("ix_products_brand", "products", ["brand"], unique=False)

    op.create_table(
        "inventory",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("stock_doc", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("stock_fact", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column("reserved_qty", sa.Numeric(14, 3), nullable=False, server_default="0"),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
            onupdate=sa.func.now(),
        ),
    )

    op.create_table(
        "stock_movements",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey("products.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("movement_type", movement_type_enum, nullable=False),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("source", sa.String(length=64), nullable=True),
        sa.Column("comment", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_stock_movements_product", "stock_movements", ["product_id"], unique=False)
    op.create_index("ix_stock_movements_type", "stock_movements", ["movement_type"], unique=False)

    op.create_table(
        "sales",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("sale_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("sale_date", sa.DateTime(timezone=True), nullable=False),
        sa.Column("source_type", source_type_enum, nullable=False),
        sa.Column("status", sale_status_enum, nullable=False),
        sa.Column("customer_name", sa.String(length=255), nullable=True),
        sa.Column("total_amount", sa.Numeric(14, 2), nullable=False),
        sa.Column("currency", sa.String(length=3), nullable=False),
        sa.Column("raw_input_text", sa.Text(), nullable=True),
        sa.Column(
            "created_by",
            sa.BigInteger(),
            sa.ForeignKey("users.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_sales_sale_date", "sales", ["sale_date"], unique=False)
    op.create_index("ix_sales_status", "sales", ["status"], unique=False)

    op.create_table(
        "sale_items",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column(
            "sale_id",
            sa.BigInteger(),
            sa.ForeignKey("sales.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "product_id",
            sa.BigInteger(),
            sa.ForeignKey("products.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("product_name_snapshot", sa.String(length=255), nullable=False),
        sa.Column("sku_snapshot", sa.String(length=64), nullable=True),
        sa.Column("quantity", sa.Numeric(14, 3), nullable=False),
        sa.Column("unit", sa.String(length=32), nullable=True),
        sa.Column("unit_price", sa.Numeric(14, 2), nullable=False),
        sa.Column("line_total", sa.Numeric(14, 2), nullable=False),
    )
    op.create_index("ix_sale_items_sale_id", "sale_items", ["sale_id"], unique=False)
    op.create_index("ix_sale_items_product_id", "sale_items", ["product_id"], unique=False)

    op.create_table(
        "documents",
        sa.Column("id", sa.BigInteger(), primary_key=True, autoincrement=True),
        sa.Column("document_type", sa.String(length=64), nullable=False),
        sa.Column(
            "related_sale_id",
            sa.BigInteger(),
            sa.ForeignKey("sales.id", ondelete="SET NULL"),
            nullable=True,
        ),
        sa.Column("document_number", sa.String(length=64), nullable=False, unique=True),
        sa.Column("file_path", sa.String(length=512), nullable=True),
        sa.Column("status", document_status_enum, nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )
    op.create_index("ix_documents_related_sale", "documents", ["related_sale_id"], unique=False)
    op.create_index("ix_documents_type", "documents", ["document_type"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_documents_type", table_name="documents")
    op.drop_index("ix_documents_related_sale", table_name="documents")
    op.drop_table("documents")

    op.drop_index("ix_sale_items_product_id", table_name="sale_items")
    op.drop_index("ix_sale_items_sale_id", table_name="sale_items")
    op.drop_table("sale_items")

    op.drop_index("ix_sales_status", table_name="sales")
    op.drop_index("ix_sales_sale_date", table_name="sales")
    op.drop_table("sales")

    op.drop_index("ix_stock_movements_type", table_name="stock_movements")
    op.drop_index("ix_stock_movements_product", table_name="stock_movements")
    op.drop_table("stock_movements")

    op.drop_table("inventory")

    op.drop_index("ix_products_brand", table_name="products")
    op.drop_index("ix_products_category", table_name="products")
    op.drop_index("ix_products_name", table_name="products")
    op.drop_table("products")

    op.drop_index("ix_users_is_active", table_name="users")
    op.drop_index("ix_users_role", table_name="users")
    op.drop_table("users")

    movement_type_enum.drop(op.get_bind())
    sale_status_enum.drop(op.get_bind())
    document_status_enum.drop(op.get_bind())
    source_type_enum.drop(op.get_bind())
    user_role_enum.drop(op.get_bind())
