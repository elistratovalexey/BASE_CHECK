# models.py
from dataclasses import dataclass
from typing import List, Optional

@dataclass
class ReceiptItem:
    item_number: int
    item_name_id: Optional[int]
    item_name: str
    quantity: float
    price: float
    sum: float
    expense_payer_id: Optional[int]

@dataclass
class Receipt:
    id: Optional[int]
    row_number: int
    receipt_date: str
    company_id: Optional[int]
    total_amount: float
    in_process: bool
    processed: bool
    process_date: Optional[str]
    payer_id: Optional[int]
    items: List[ReceiptItem] = None

    def __post_init__(self):
        if self.items is None:
            self.items = []