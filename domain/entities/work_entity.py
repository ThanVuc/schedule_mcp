from dataclasses import dataclass, field
from typing import List


@dataclass
class Work:
    name: str
    short_descriptions: str
    detailed_description: str
    start_date: str
    end_date: str
    difficulty_key: str
    priority_key: str
    category_key: str
    sub_tasks: List[str] = field(default_factory=list)
