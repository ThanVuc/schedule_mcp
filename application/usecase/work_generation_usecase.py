
import asyncio
from functools import partial
import json
import logging
from application.dtos.work_generation_dto import WorkGenerationMessageDTO
from application.publisher.notification_publisher import NotificationPublisher
from application.publisher.work_transfer_publisher import WorkTransferPublisher
from domain.entities.notification_entity import Notification
from domain.entities.work_entity import Work
from domain.prompt.work_generation_prompt import BuildWorkGenerationPrompt
from infrastructure.base.llm.gemini_llm import LLMConnector


class WorkGenerationUseCase:
    def __init__(
            self, 
            llm: LLMConnector,
            notification_publisher: NotificationPublisher,
            work_transfer_publisher: WorkTransferPublisher
    ):
        self.llm = llm
        self.notification_publisher = notification_publisher
        self.work_transfer_publisher = work_transfer_publisher
    
    async def generate_work(
        self,
        dto: WorkGenerationMessageDTO,
        message_id: str
    ):
        prompt = BuildWorkGenerationPrompt(dto)
        response = ""
        try:
            response = str(await self.llm.generate(
                prompt=prompt,
                max_output_tokens=15000,
                temperature=0.1,
                top_p=0.8,
                top_k=40,
                afc_enabled=False
            ))

            if not response:
                raise ValueError("LLM returned empty response")
            
            response = response.strip()

            if response.startswith("```"):
                response = response.split("```")[1]
                response = response.replace("json", "", 1).strip()

            raw_works = json.loads(response)
            works = [
                Work(
                    name=item["name"],
                    short_descriptions=item["short_descriptions"],
                    detailed_description=item.get("detailed_description", ""),
                    start_date=f"{dto.local_date} {item['start_date']}",
                    end_date=f"{dto.local_date} {item['end_date']}",
                    difficulty_key=item["difficulty"],
                    priority_key=item["priority"],
                    category_key=item["category"],
                    sub_tasks=item.get("sub_tasks", []),
                )
                for item in raw_works
            ]

            await self.work_transfer_publisher.publish(works, dto, message_id)
        except Exception as e:
            logging.error("Failed to generate works: %s", str(e))
            self.notification_publisher.publish(
                Notification(
                    title="Tạo công việc với AI thất bại",
                    message="Hệ thống gặp lỗi khi tạo công việc cho bạn. Vui lòng thử lại sau.",
                    sender_id="system",
                    receiver_ids=[dto.user_id],
                    correlation_id=message_id,
                    correlation_type=2,
                )
            )

