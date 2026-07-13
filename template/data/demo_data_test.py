"""Demo tests for data adapter templates."""
from __future__ import annotations

from pathlib import Path

import pytest

from template.data.demo_data_adapter import DemoDataContainer


@pytest.mark.asyncio
async def test_demo_data_container_can_initialize():
    local_dir = Path("data") / "template_demo"
    local_dir.mkdir(parents=True, exist_ok=True)
    db_path = str(local_dir / "demo_data.db")
    dc = DemoDataContainer(db_path=db_path)
    await dc.initialize()
    # We only verify startup path in this template test.
    assert dc is not None
