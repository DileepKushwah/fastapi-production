import logging
import time
import uuid
import json
import hashlib
import asyncio
from contextlib import asynccontextmanager
from datetime import datetime

import structlog
from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text, select
from sqlalchemy.ext.asyncio import AsyncSession
from prometheus_fastapi_instrumentator import Instrumentator

from app.database import engine, get_db, Base
from app.models import Item, AISummary
from app.schemas import ItemCreate, ItemResponse, HealthResponse, SummarizeRequest, SummarizeResponse
from app.config import settings
from app.cache import get_redis, close_redis

# Setup Logging
structlog.configure(
    processors=[
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.JSONRenderer(),
    ],
)
log = structlog.get_logger()

# App Startup & Shutdown
@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("startup", message="Creating database tables...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    log.info("startup", message="App is ready!")
    yield
    await close_redis()
    await engine.dispose()
    log.info("shutdown", message="App stopped cleanly")

# Create App
app = FastAPI(
    title="Production API",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.ALLOWED_ORIGINS,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Expose metrics endpoint (/metrics) for Prometheus
Instrumentator().instrument(app).expose(app)

# Log Every Request
@app.middleware("http")
async def logging_middleware(request: Request, call_next):
    request_id = str(uuid.uuid4())
    start = time.perf_counter()
    response = await call_next(request)
    duration = round((time.perf_counter() - start) * 1000, 2)
    log.info("request",
        method=request.method,
        path=request.url.path,
        status=response.status_code,
        duration_ms=duration,
        request_id=request_id
    )
    response.headers["X-Request-ID"] = request_id
    return response

# Health Check (Database and Redis liveness/readiness check)
@app.get("/health", tags=["Health"])
async def health_check(db: AsyncSession = Depends(get_db)):
    checks = {}
    try:
        await db.execute(text("SELECT 1"))
        checks["database"] = "ok"
    except Exception as e:
        log.error("health_check_db_failed", error=str(e))
        checks["database"] = "error"
        
    try:
        r = await get_redis()
        await r.ping()
        checks["redis"] = "ok"
    except Exception as e:
        log.error("health_check_redis_failed", error=str(e))
        checks["redis"] = "error"

    status = "healthy" if all(v == "ok" for v in checks.values()) else "degraded"
    code = 200 if status == "healthy" else 503

    return JSONResponse(status_code=code, content={
        "status": status,
        "checks": checks,
        "timestamp": datetime.utcnow().isoformat(),
        "version": app.version
    })

@app.get("/health/live", tags=["Health"])
async def liveness():
    return {"status": "alive"}

# Items API
@app.post("/items", status_code=201, tags=["Items"])
async def create_item(
    payload: ItemCreate,
    db: AsyncSession = Depends(get_db)
):
    item = Item(**payload.model_dump())
    db.add(item)
    await db.commit()
    await db.refresh(item)
    r = await get_redis()
    await r.delete("items:all")
    log.info("item_created", item_id=item.id)
    return item

@app.get("/items", tags=["Items"])
async def list_items(db: AsyncSession = Depends(get_db)):
    r = await get_redis()
    cached = await r.get("items:all")
    if cached:
        return json.loads(cached)
    result = await db.execute(
        select(Item).order_by(Item.created_at.desc())
    )
    items = result.scalars().all()
    serialized = [
        {
            "id": i.id,
            "name": i.name,
            "description": i.description,
            "created_at": i.created_at.isoformat()
        }
        for i in items
    ]
    await r.setex("items:all", 60, json.dumps(serialized))
    return items

@app.get("/items/{item_id}", tags=["Items"])
async def get_item(
    item_id: int,
    db: AsyncSession = Depends(get_db)
):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    return item

@app.delete("/items/{item_id}", status_code=204, tags=["Items"])
async def delete_item(
    item_id: int,
    db: AsyncSession = Depends(get_db)
):
    item = await db.get(Item, item_id)
    if not item:
        raise HTTPException(status_code=404, detail="Item not found")
    await db.delete(item)
    await db.commit()
    r = await get_redis()
    await r.delete("items:all")
    log.info("item_deleted", item_id=item_id)

# AI / LLM Mock Summarization Endpoint
@app.post("/ai/summarize", response_model=SummarizeResponse, status_code=200, tags=["AI"])
async def summarize_text(
    payload: SummarizeRequest,
    db: AsyncSession = Depends(get_db)
):
    text_content = payload.text.strip()
    
    # Calculate SHA256 of the text to use as Cache Key and reference
    text_hash = hashlib.sha256(text_content.encode("utf-8")).hexdigest()
    cache_key = f"ai:summary:{text_hash}"
    
    r = await get_redis()
    
    # Check cache
    cached_summary = await r.get(cache_key)
    if cached_summary:
        log.info("ai_summary_cache_hit", hash=text_hash)
        return SummarizeResponse(
            summary=cached_summary,
            execution_time_ms=0.0,
            cached=True,
            created_at=datetime.utcnow()
        )
    
    # Simulate LLM/AI model processing time (500ms latency)
    start_time = time.perf_counter()
    await asyncio.sleep(0.5)
    
    # Simple extractive summarization logic: split sentences and take top 2 longest ones
    sentences = [s.strip() for s in text_content.split(".") if len(s.strip()) > 3]
    if len(sentences) <= 2:
        summary_text = "Summary: " + text_content
    else:
        # Sort by length as a proxy for information content
        sorted_sentences = sorted(sentences, key=len, reverse=True)
        summary_text = f"Summary: {sorted_sentences[0]}. {sorted_sentences[1]}."
    
    duration = round((time.perf_counter() - start_time) * 1000, 2)
    
    # Store in database
    ai_entry = AISummary(
        text_hash=text_hash,
        original_text=text_content,
        summary=summary_text,
        execution_time_ms=duration
    )
    db.add(ai_entry)
    await db.commit()
    await db.refresh(ai_entry)
    
    # Cache result in Redis for 1 hour (3600 seconds)
    await r.setex(cache_key, 3600, summary_text)
    
    log.info("ai_summary_generated", hash=text_hash, duration_ms=duration)
    
    return SummarizeResponse(
        summary=summary_text,
        execution_time_ms=duration,
        cached=False,
        created_at=ai_entry.created_at
    )