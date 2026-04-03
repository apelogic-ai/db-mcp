async def report_progress(ctx, progress: float, total: float = 100) -> None:
    if ctx is None:
        return
    try:
        await ctx.report_progress(progress=progress, total=total)
    except Exception:
        pass
