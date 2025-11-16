import os
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from database import db, create_document, get_documents
from schemas import Transaction, CategoryRule, Budget
from bson import ObjectId

app = FastAPI(title="Spend Tracker API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/")
def read_root():
    return {"message": "Spend Tracker API is running"}


@app.get("/test")
def test_database():
    """Test endpoint to check if database is available and accessible"""
    response = {
        "backend": "✅ Running",
        "database": "❌ Not Available",
        "database_url": None,
        "database_name": None,
        "connection_status": "Not Connected",
        "collections": []
    }

    try:
        if db is not None:
            response["database"] = "✅ Available"
            response["database_url"] = "✅ Configured"
            response["database_name"] = db.name if hasattr(db, 'name') else "✅ Connected"
            response["connection_status"] = "Connected"
            try:
                collections = db.list_collection_names()
                response["collections"] = collections[:10]
                response["database"] = "✅ Connected & Working"
            except Exception as e:
                response["database"] = f"⚠️  Connected but Error: {str(e)[:50]}"
        else:
            response["database"] = "⚠️  Available but not initialized"

    except Exception as e:
        response["database"] = f"❌ Error: {str(e)[:50]}"

    response["database_url"] = "✅ Set" if os.getenv("DATABASE_URL") else "❌ Not Set"
    response["database_name"] = "✅ Set" if os.getenv("DATABASE_NAME") else "❌ Not Set"

    return response


# ---------- Helpers ----------

def apply_auto_category(merchant: str, description: Optional[str]) -> Optional[str]:
    """Return a category if any rule keyword matches merchant or description."""
    text = f"{merchant} {description or ''}".lower()
    rules = get_documents("categoryrule")
    for r in rules:
        if r.get("keyword", "").lower() in text:
            return r.get("category")
    return None


def month_from_date(dt: datetime) -> str:
    return dt.strftime("%Y-%m")


# ---------- Transactions ----------

class TransactionIn(Transaction):
    pass

class TransactionOut(BaseModel):
    id: str
    amount: float
    merchant: str
    description: Optional[str]
    category: Optional[str]
    date: datetime
    account: Optional[str]
    currency: str


def normalize_txn(doc: Dict[str, Any]) -> TransactionOut:
    return TransactionOut(
        id=str(doc.get("_id")),
        amount=doc.get("amount"),
        merchant=doc.get("merchant"),
        description=doc.get("description"),
        category=doc.get("category"),
        date=doc.get("date"),
        account=doc.get("account"),
        currency=doc.get("currency", "USD"),
    )


@app.post("/api/transactions", response_model=TransactionOut)
def create_transaction(payload: TransactionIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    data = payload.model_dump()
    auto = apply_auto_category(data["merchant"], data.get("description"))
    if auto and not data.get("category"):
        data["category"] = auto
    inserted_id_str = create_document("transaction", data)
    try:
        doc = db["transaction"].find_one({"_id": ObjectId(inserted_id_str)})
    except Exception:
        # Fallback: best-effort fetch by fields with latest timestamp
        doc = db["transaction"].find_one({"merchant": data["merchant"], "amount": data["amount"]}, sort=[("created_at", -1)])
    if not doc:
        raise HTTPException(status_code=500, detail="Failed to fetch created transaction")
    return normalize_txn(doc)


@app.get("/api/transactions", response_model=List[TransactionOut])
def list_transactions(limit: int = Query(100, ge=1, le=1000), category: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    filt: Dict[str, Any] = {}
    if category:
        filt["category"] = category
    docs = db["transaction"].find(filt).sort("date", -1).limit(limit)
    return [normalize_txn(d) for d in docs]


@app.get("/api/insights")
def insights(month: Optional[str] = None):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    """Return monthly totals by category and simple budget recommendations."""
    if month is None:
        month = datetime.utcnow().strftime("%Y-%m")
    start = datetime.strptime(month + "-01", "%Y-%m-%d")
    end = (start + timedelta(days=32)).replace(day=1)

    pipeline = [
        {"$match": {"date": {"$gte": start, "$lt": end}}},
        {"$group": {"_id": "$category", "total": {"$sum": "$amount"}, "count": {"$sum": 1}}},
        {"$sort": {"total": -1}},
    ]
    agg = list(db["transaction"].aggregate(pipeline))

    budgets = {b["category"]: b for b in db["budget"].find({"month": month})}

    recommendations = []
    for item in agg:
        cat = item.get("_id") or "Uncategorized"
        total = item.get("total", 0)
        limit = budgets.get(cat, {}).get("limit")
        if limit:
            used_pct = round((total / limit) * 100, 1)
            if used_pct >= 90:
                msg = f"You're at {used_pct}% of your {cat} budget. Consider reducing spend or raising your limit."
            elif used_pct >= 70:
                msg = f"{cat} spending is trending high at {used_pct}%. Keep an eye on it."
            else:
                msg = f"{cat} spending is healthy at {used_pct}%."
        else:
            msg = f"No budget set for {cat}. Consider adding one to track spending."
        recommendations.append({
            "category": cat,
            "spent": round(total, 2),
            "budget": limit,
            "message": msg
        })

    summary = {
        "month": month,
        "categories": recommendations,
        "top_category": recommendations[0]["category"] if recommendations else None,
        "total_spend": round(sum(i.get("spent", 0) for i in recommendations), 2)
    }
    return summary


# ---------- Rules & Budgets ----------

class RuleIn(CategoryRule):
    pass

@app.post("/api/rules")
def add_rule(rule: RuleIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    create_document("categoryrule", rule)
    return {"status": "ok"}


class BudgetIn(Budget):
    pass

@app.post("/api/budgets")
def set_budget(budget: BudgetIn):
    if db is None:
        raise HTTPException(status_code=500, detail="Database not available")
    create_document("budget", budget)
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
