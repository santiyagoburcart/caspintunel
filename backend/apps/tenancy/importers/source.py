"""The neutral shape every source adapter returns (v1.56 store import). The engine (`engine.py`) only sees these."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class Customer:
    key: str                         # stable id in the source (Mirza: the Telegram id)
    telegram_id: int
    telegram_username: str = ""
    phone: str = ""
    balance: int = 0                 # tomans
    blocked: bool = False
    agent: bool = False
    referrer_key: str = ""
    joined_at: datetime | None = None
    language: str = "fa"


@dataclass
class Product:
    key: str
    name: str
    volume_gb: int = 0
    days: int = 0
    price: int = 0
    location: str = ""
    for_agents: bool = False


@dataclass
class Service:
    key: str
    customer_key: str
    panel_username: str
    product_name: str = ""
    volume_gb: int = 0
    days: int = 0
    price: int = 0
    sold_at: datetime | None = None
    location: str = ""
    status: str = ""
    sold: bool = False               # the bot delivered it (not unpaid / failed / removed)
    live: bool = False               # active or not started yet in the bot


@dataclass
class Payment:
    key: str
    customer_key: str
    amount: int
    status: str
    paid: bool
    method: str = ""
    at: datetime | None = None
    kind: str = "other"              # buy | renew | wallet | other
    ref: str = ""


@dataclass
class Source:
    system: str
    label: str
    panels: list = field(default_factory=list)
    customers: list[Customer] = field(default_factory=list)
    products: list[Product] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    payments: list[Payment] = field(default_factory=list)
