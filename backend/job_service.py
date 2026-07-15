"""
Job scraping + resume matching, scoped per session via an ephemeral,
in-memory-only Chroma collection. chromadb.Client() with no
persist_directory keeps everything in RAM — nothing touches disk. Each
session gets its own uniquely-named collection, dropped whenever a new
search runs or the session ends.
"""
import os
import uuid

import chromadb
from apify_client import ApifyClient
from langchain_chroma import Chroma
from langchain_core.documents import Document
from langchain_huggingface import HuggingFaceEmbeddings

APIFY_API_TOKEN = os.getenv("APIFY_API_TOKEN")

# Loaded once at process startup and shared read-only across all sessions —
# this is a stateless model, not per-user data, so sharing it is fine.
# _embeddings = HuggingFaceEmbeddings(model_name="sentence-transformers/all-MiniLM-L6-v2")
_embeddings = None

def get_embeddings():
    global _embeddings
    if _embeddings is None:
        _embeddings = HuggingFaceEmbeddings(
            model_name="sentence-transformers/all-MiniLM-L6-v2"
        )
    return _embeddings

# In-memory Chroma client (no persist_directory => RAM only, gone on restart).
_chroma_client = chromadb.Client()


def _get_session_vector_store(session) -> Chroma:
    if not session.vector_collection_name:
        session.vector_collection_name = f"session-{uuid.uuid4().hex}"
    return Chroma(
        client=_chroma_client,
        collection_name=session.vector_collection_name,
        embedding_function=get_embeddings(),
    )


def clear_session_jobs(session) -> None:
    """Drop this session's ephemeral vector collection, if any, before a
    fresh search — mirrors clear_jobs_collection() in the original script."""
    if session.vector_collection_name:
        try:
            _chroma_client.delete_collection(session.vector_collection_name)
        except Exception:
            pass
        session.vector_collection_name = None
    session.last_matches = []


def scrape_jobs(keywords: str, location: str = "", count: int = 30) -> list[dict]:
    apify_client = ApifyClient(APIFY_API_TOKEN)
    query = keywords.replace(" ", "%20")
    search_url = f"https://www.linkedin.com/jobs/search/?keywords={query}"
    if location:
        search_url += f"&location={location.replace(' ', '%20')}"
    run = apify_client.actor("curious_coder/linkedin-jobs-scraper").call(
        run_input={"urls": [search_url], "scrapeCompany": False, "count": count}
    )
    return list(apify_client.dataset(run["defaultDatasetId"]).iterate_items())


def search_and_match(session, keywords: str, location: str, k: int = 5) -> list[dict]:
    if not session.resume_text:
        raise ValueError("Upload a resume first.")

    clear_session_jobs(session)
    items = scrape_jobs(keywords, location)

    docs, ids = [], []
    for item in items:
        url = item.get("url") or item.get("jobUrl") or item.get("link")
        if not url:
            continue
        title = item.get("title", "Unknown title")
        company = item.get("companyName") or item.get("company", "Unknown company")
        loc = item.get("location", "")
        description = item.get("description") or item.get("descriptionText") or ""
        page_content = f"{title} at {company} ({loc})\n\n{description}"[:4000]
        docs.append(
            Document(
                page_content=page_content,
                metadata={"url": url, "title": title, "company": company, "location": loc},
            )
        )
        ids.append(url)

    if not docs:
        return []

    vector_store = _get_session_vector_store(session)
    vector_store.add_documents(docs, ids=ids)

    results = vector_store.similarity_search(session.resume_text, k=k)
    matches = [
        {
            "title": d.metadata["title"],
            "company": d.metadata["company"],
            "location": d.metadata["location"],
            "url": d.metadata["url"],
            "summary": d.page_content[:400],
        }
        for d in results
    ]
    session.last_matches = matches
    return matches
