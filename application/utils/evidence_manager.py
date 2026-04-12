import json
import logging
import shutil
import base64
from pathlib import Path
from typing import Any

from pydantic import BaseModel

logger = logging.getLogger(__name__)


class EvidenceManager:
    """Manages saving pipeline step results as evidence to z_evidence folder."""

    def __init__(self, evidence_dir: str = "z_evidence"):
        self.evidence_dir = Path(evidence_dir)
        self.ensure_dir_exists()

    def ensure_dir_exists(self):
        """Ensure the evidence directory exists."""
        self.evidence_dir.mkdir(parents=True, exist_ok=True)

    def clear_evidence(self):
        """Clear all evidence folders before starting a new pipeline run."""
        try:
            if self.evidence_dir.exists():
                shutil.rmtree(self.evidence_dir)
            self.ensure_dir_exists()
            logger.info("Evidence directory cleared: %s", self.evidence_dir)
        except Exception:
            logger.exception("Failed to clear evidence directory")
            raise

    def save_step_result(self, step_name: str, result: Any, file_name: str = "result.json"):
        """
        Save the result of a pipeline step as JSON evidence.

        Args:
            step_name: Name of the pipeline step (e.g., 'ingestion', 'normalization')
            result: The result object to save (Pydantic model, dict, list, etc.)
            file_name: Optional custom file name (default: result.json)
        """
        try:
            step_dir = self.evidence_dir / step_name
            step_dir.mkdir(parents=True, exist_ok=True)

            # Serialize the result
            if isinstance(result, BaseModel):
                # Pydantic model
                data = result.model_dump()
            elif isinstance(result, list) and len(result) > 0 and isinstance(result[0], BaseModel):
                # List of Pydantic models
                data = [item.model_dump() if isinstance(item, BaseModel) else item for item in result]
            elif isinstance(result, dict):
                data = result
            elif isinstance(result, list):
                data = result
            else:
                # Fallback: convert to dict if it has __dict__
                data = result.__dict__ if hasattr(result, "__dict__") else result

            output_file = step_dir / file_name
            json_content = json.dumps(self._json_safe(data), ensure_ascii=False, indent=2)

            with open(output_file, "w", encoding="utf-8") as f:
                f.write(json_content)

            logger.info("Evidence saved: %s/%s", step_name, file_name)
        except Exception:
            logger.exception("Failed to save evidence for step: %s", step_name)
            raise

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if isinstance(value, bytes):
            return base64.b64encode(value).decode("ascii")
        if isinstance(value, dict):
            return {k: cls._json_safe(v) for k, v in value.items()}
        if isinstance(value, list):
            return [cls._json_safe(v) for v in value]
        return value

    def save_step_results_multiple(self, step_name: str, results: dict[str, Any]):
        """
        Save multiple results for a single step.

        Args:
            step_name: Name of the pipeline step
            results: Dict of {file_name: result_data}
        """
        for file_name, result in results.items():
            self.save_step_result(step_name, result, file_name)
