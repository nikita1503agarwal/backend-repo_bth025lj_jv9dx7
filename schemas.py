"""
Database Schemas for Spend Tracker

Each Pydantic model corresponds to one MongoDB collection (lowercased class name).
"""
from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime

class Transaction(BaseModel):
    """
    Collection: "transaction"
    A single financial transaction.
    """
    amount: float = Field(..., gt=0, description="Transaction amount (positive number)")
    merchant: str = Field(..., description="Merchant or payee name")
    description: Optional[str] = Field(None, description="Optional description or memo")
    category: Optional[str] = Field(None, description="Assigned category (auto or manual)")
    date: datetime = Field(..., description="Transaction date/time in ISO format")
    account: Optional[str] = Field(None, description="Account name or type (e.g., Checking)")
    currency: str = Field("USD", description="Currency code")

class CategoryRule(BaseModel):
    """
    Collection: "categoryrule"
    Auto-categorization rule using a keyword match on merchant/description.
    """
    keyword: str = Field(..., description="Lowercased keyword to match (e.g., 'starbucks')")
    category: str = Field(..., description="Category to assign when keyword matches")

class Budget(BaseModel):
    """
    Collection: "budget"
    Budget limit per category per month (YYYY-MM).
    """
    category: str = Field(..., description="Category name")
    month: str = Field(..., pattern=r"^\d{4}-\d{2}$", description="Month in format YYYY-MM")
    limit: float = Field(..., gt=0, description="Spending limit for this category and month")

# Example list of common categories that the UI may suggest
class CategorySuggestion(BaseModel):
    name: str
    icon: Optional[str] = None

DEFAULT_CATEGORIES: List[CategorySuggestion] = [
    CategorySuggestion(name="Groceries", icon="shopping-basket"),
    CategorySuggestion(name="Dining", icon="utensils"),
    CategorySuggestion(name="Transport", icon="car"),
    CategorySuggestion(name="Shopping", icon="shopping-bag"),
    CategorySuggestion(name="Entertainment", icon="film"),
    CategorySuggestion(name="Bills", icon="credit-card"),
    CategorySuggestion(name="Health", icon="heart"),
    CategorySuggestion(name="Travel", icon="plane"),
    CategorySuggestion(name="Other", icon="circle")
]
