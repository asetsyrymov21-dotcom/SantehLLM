import argparse
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.models.product import Product
from app.rag import indexer
from app.services.search_service import SearchService


def get_session_factory():
    url = os.getenv("DATABASE_URL", "sqlite:///./app.db")
    engine = create_engine(url)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)
    return SessionLocal


def do_reindex():
    SessionLocal = get_session_factory()
    with SessionLocal() as session:
        products = session.query(Product).all()
        if not products:
            print("Каталог пуст: индексировать нечего.")
            return
        count = indexer.index_products(session, products, tenant_id=None)
        session.commit()
        print(f"Проиндексировано товаров: {count}")


def do_search(query: str, limit: int, mode: str):
    SessionLocal = get_session_factory()
    svc = SearchService(SessionLocal)
    if mode == "keyword":
        with SessionLocal() as session:
            hits = svc._keyword_product_search(session, query=query, limit=limit, tenant_id=None)
            for h in hits:
                print(f"[keyword] pid={h.product_id} score={h.score:.3f} text={h.searchable_text[:80]}")
        return

    if mode == "semantic":
        with SessionLocal() as session:
            hits = svc.semantic_product_search(query=query, limit=limit)
            for h in hits:
                print(f"[semantic] pid={h.product_id} score={h.score:.3f} text={h.searchable_text[:80]}")
        return

    # merged
    results = svc.search_products(query=query, limit=limit)
    for item in results:
        prod = item["product"]
        print(
            f"[{item['match_type']}] pid={prod.id} sku={getattr(prod,'sku',None)} "
            f"name={prod.name} score={item['score']:.3f} brand={getattr(prod,'brand', '')}"
        )


def main():
    parser = argparse.ArgumentParser(description="Product search debug CLI")
    parser.add_argument("query", nargs="?", help="Search query")
    parser.add_argument("--limit", type=int, default=5)
    parser.add_argument("--mode", choices=["keyword", "semantic", "merged"], default="merged")
    parser.add_argument("--reindex", action="store_true", help="Reindex products first")
    args = parser.parse_args()

    if args.reindex:
        do_reindex()

    if args.query:
        do_search(args.query, args.limit, args.mode)
    else:
        print("Укажите query или --reindex")


if __name__ == "__main__":
    main()
