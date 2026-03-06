# services/bank_import/models.py

from __future__ import annotations

from dataclasses import dataclass, asdict
from typing import Optional


@dataclass
class ParsedStatementOperation:
    bank_name: str
    operation_date: str          # YYYY-MM-DD
    amount: float
    currency: str
    tx_type: str                 # income / expense
    description: str
    raw_description: str
    external_id: Optional[str] = None
    mcc: Optional[str] = None
    merchant: Optional[str] = None

    def to_dict(self) -> dict:
        return asdict(self)

    @staticmethod
    def from_dict(data: dict) -> "ParsedStatementOperation":
        return ParsedStatementOperation(**data)