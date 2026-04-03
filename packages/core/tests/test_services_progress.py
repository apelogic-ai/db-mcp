from unittest.mock import AsyncMock, MagicMock

import pytest

from db_mcp.services.progress import report_progress


@pytest.mark.asyncio
async def test_report_progress_forwards_to_context_reporter():
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()

    await report_progress(ctx, progress=25, total=80)

    ctx.report_progress.assert_awaited_once_with(progress=25, total=80)
