"""
本地整合包扫描 API 路由

提供本地目录扫描、候选发现、状态查询、内容提取端点。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.pack_scan import (
    DiscoverResultData,
    ExtractRequest,
    PackDiscoverRequest,
    PackScanRequest,
    ScanResultData,
    ScanStatusData,
)
from ..services.pack_scanner import PackScanError, PackScannerService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/pack-scan", tags=["pack-scan"])
pack_scanner = PackScannerService()


@router.post("/discover")
async def discover_pack_folder(
    body: PackDiscoverRequest,
):
    """发现本地整合包目录中的游戏实例候选。"""
    try:
        result = pack_scanner.discover_directory(body.local_path)
        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except PackScanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to discover pack folder: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("")
async def scan_pack_folder(
    body: PackScanRequest,
    db: Session = Depends(get_db),
):
    """扫描本地整合包目录，检测类型、版本和待翻译区域。"""
    try:
        local_path = body.local_path
        if body.platform:
            pass

        result = pack_scanner.scan_directory(local_path, body.game_name)
        pack_scanner.save_to_db(db, local_path, result)

        return {
            "code": 0,
            "data": result,
            "message": "ok",
        }
    except PackScanError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error("Failed to scan pack folder: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{scan_id}/status")
async def get_scan_status(scan_id: str):
    """查询扫描进度。"""
    try:
        status = pack_scanner.get_status(scan_id)
        if status is None:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        return {
            "code": 0,
            "data": status,
            "message": "ok",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get scan status: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{scan_id}/areas")
async def get_scan_areas(scan_id: str):
    """获取检测到的待翻译区域详情。"""
    try:
        cache = pack_scanner._scan_cache.get(scan_id)
        if cache is None:
            raise HTTPException(status_code=404, detail=f"Scan {scan_id} not found")
        result = cache.get("result", {})
        return {
            "code": 0,
            "data": result.get("areas", []),
            "message": "ok",
        }
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Failed to get scan areas: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{scan_id}/extract")
async def extract_content(
    scan_id: str,
    body: ExtractRequest = None,
):
    """提取待翻译内容，返回条目列表。"""
    try:
        selected = body.selected_areas if body else None
        tasks = pack_scanner.extract_content(scan_id, selected)
        return {
            "code": 0,
            "data": {
                "scan_id": scan_id,
                "total_entries": len(tasks),
                "items": tasks,
            },
            "message": "ok",
        }
    except PackScanError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to extract content: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
