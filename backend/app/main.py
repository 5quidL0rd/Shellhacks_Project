"""FastAPI app. Story Mode endpoints only - the feed, graph, and research
endpoints in plans.md belong to the backend owner and land alongside these.
"""
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .connections import connections
from .story.build import get_story
from .story.schema import Story
from .universe import COMPANIES, SYMBOLS

app = FastAPI(title="Portfolio Story API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "universe": list(SYMBOLS)}


@app.get("/universe")
def universe() -> list[dict]:
    return [
        {
            "symbol": c.symbol, "name": c.name, "sector": c.sector,
            "peers": [link.symbol for link in connections(c.symbol)],
            "connections": [
                {"symbol": link.symbol, "relationship": link.label,
                 "detail": link.detail, "source": link.source}
                for link in connections(c.symbol)
            ],
        }
        for c in COMPANIES.values()
    ]


@app.get("/story/{symbol}", response_model=Story)
def story(symbol: str, refresh: bool = Query(default=False)) -> Story:
    """Price series plus labelled, cited explanations of each major move."""
    try:
        return get_story(symbol, refresh=refresh)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from None
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from None


@app.get("/story/{symbol}/citation/{citation_id}")
def citation(symbol: str, citation_id: str) -> dict:
    """Backs the drill-down panel: the numbers and the outbound source link."""
    story_obj = get_story(symbol)
    item = story_obj.evidence.get(citation_id)
    if item is None:
        raise HTTPException(status_code=404, detail=f"No evidence {citation_id}")
    return item.model_dump(mode="json")
