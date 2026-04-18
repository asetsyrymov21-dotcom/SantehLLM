import types

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.db.base import Base
from app.models.product import Product
from app.rag import indexer
from app.rag.embeddings import embed_texts
from app.rag.retrieval_products import semantic_product_search, _vector_candidates
from app.services.search_service import SearchService
from app.rag.schemas import ProductEmbedding


@pytest.fixture()
def session_factory(monkeypatch):
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine)
    return SessionLocal


@pytest.fixture(autouse=True)
def stub_embeddings(monkeypatch):
    """
    Deterministic embeddings: map text to simple 2d vectors.
    """

    def _fake_embed_texts(texts, model=None):
        out = []
        for t in texts:
            t = t.lower()
            if "red" in t:
                out.append([1.0, 0.0])
            elif "blue" in t:
                out.append([0.0, 1.0])
            else:
                out.append([0.5, 0.5])
        return out

    monkeypatch.setattr("app.rag.embeddings.embed_texts", _fake_embed_texts)
    return _fake_embed_texts


def seed_products(session_factory):
    with session_factory() as session:
        session.add_all(
            [
                Product(name="Red Shoe", brand="Nike", category="Shoes", description="Light red running shoe"),
                Product(name="Blue Shirt", brand="Uniqlo", category="Shirts", description="Blue cotton shirt"),
            ]
        )
        session.commit()


def test_index_products_creates_embeddings(session_factory):
    seed_products(session_factory)
    with session_factory() as session:
        products = session.query(Product).all()
        count = indexer.index_products(session, products, tenant_id=None)
        session.commit()
        assert count == 2
        assert session.query(ProductEmbedding).count() == 2


def test_semantic_product_search_returns_ranked(session_factory):
    seed_products(session_factory)
    with session_factory() as session:
        products = session.query(Product).all()
        indexer.index_products(session, products, tenant_id=None)
        session.commit()

    with session_factory() as session:
        hits = semantic_product_search(session, "red shoe", tenant_id=None, limit=1)
        assert len(hits) == 1
        assert hits[0].product_id == 1


def test_search_products_merges_keyword_and_semantic(session_factory, monkeypatch):
    seed_products(session_factory)
    with session_factory() as session:
        products = session.query(Product).all()
        indexer.index_products(session, products, tenant_id=None)
        session.commit()

    # Force semantic to return product 2 as well
    def fake_semantic(session, query, tenant_id=None, limit=5, **kwargs):
        return [
            types.SimpleNamespace(product_id=2, score=0.9, searchable_text="blue shirt", source="semantic"),
        ]

    monkeypatch.setattr("app.rag.retrieval_products.semantic_product_search", fake_semantic)

    search = SearchService(session_factory)
    results = search.search_products("red", limit=3)
    ids = [p.id for p in results]
    # keyword hit product 1, semantic hit product 2; both should appear without duplicates
    assert ids == [1, 2]
