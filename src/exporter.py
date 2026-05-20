from pathlib import Path
from typing import Optional

from src.config import AppConfig
from src.database import Database
from src.models import UsernameStatus


class ResultExporter:
    def __init__(self, config: AppConfig, db: Database):
        self.config = config
        self.db = db

    async def export_available_txt(self, run_id: str, path: Optional[str] = None) -> str:
        output_path = path or str(Path(self.config.output_dir) / "available.txt")
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)

        candidates = await self.db.get_candidates_by_status(UsernameStatus.AVAILABLE, run_id)
        with open(output_path, "w", encoding="utf-8") as f:
            for c in candidates:
                f.write(f"{c.username}\n")

        return output_path

    async def export_all(self, run_id: str) -> dict[str, str]:
        return {
            "txt": await self.export_available_txt(run_id),
        }
