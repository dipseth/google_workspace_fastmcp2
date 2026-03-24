"""Symbol table endpoints."""
from fastapi import APIRouter, HTTPException

router = APIRouter(tags=["symbols"])


@router.get("/symbols")
async def get_symbols():
    """Return the full symbol table with forward and reverse mappings."""
    try:
        from gchat.wrapper_api import get_gchat_symbols
        symbols = get_gchat_symbols()
        reverse = {v: k for k, v in symbols.items()}
        return {
            "symbols": symbols,
            "reverse": reverse,
            "count": len(symbols),
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
