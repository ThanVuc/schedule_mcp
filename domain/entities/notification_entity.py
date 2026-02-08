from dataclasses import dataclass, field
from typing import List, Optional
from datetime import timezone, datetime

from constant.notification import AI_MCP_CORRELATION_TYPE


@dataclass
class Notification:
    id: Optional[str] = None
    title: str = "AI tạo công việc"
    message: str = ""
    link: Optional[str] = "https://www.schedulr.site/schedule/daily"
    sender_id: str = ""
    receiver_ids: List[str] = field(default_factory=list)
    img_url: Optional[str] = ""
    correlation_id: str = ""
    correlation_type: int = AI_MCP_CORRELATION_TYPE
