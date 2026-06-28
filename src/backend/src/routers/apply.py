"""
应用翻译 API 路由

提供翻译应用、备份管理、恢复操作等端点。
"""

import logging
import os

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session

from ..database import get_db
from ..schemas.apply import BackupRecordResponse, RestoreResponse
from ..schemas.resourcepack import (
    GeneratePatchPackageResponse,
    GenerateResourcePackResponse,
    PatchPackageConfig,
    ResourcePackConfig,
)
from ..services.apply_service import ApplyService
from ..services.resourcepack_service import ResourcePackService

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/v1/apply", tags=["apply"])
apply_service = ApplyService()
resourcepack_service = ResourcePackService()


def _build_resourcepack_response(task_id: int, result: dict) -> dict:
    return GenerateResourcePackResponse(
        resourcepack_id=result.get("resourcepack_id", ""),
        download_url=f"/api/v1/apply/{task_id}/download-resourcepack",
        filename=result.get("filename", "resourcepack.zip"),
        file_path=result.get("file_path", ""),
        file_size=result.get("file_size", 0),
        pack_format=result.get("pack_format", 0),
        item_count=result.get("item_count", 0),
    ).model_dump()


@router.post("/{task_id}")
async def apply_translation(
    task_id: int,
    local_path: str | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        record = await apply_service.apply_translation(db=db, task_id=task_id, local_path=local_path)
        data = BackupRecordResponse(**apply_service.serialize_backup_record(record)).model_dump()
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to apply translation: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/restore")
async def restore_translation(
    task_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = await apply_service.restore_translation_for_task(db=db, task_id=task_id)
        data = RestoreResponse(
            restored_files=result.get("restored_files", []),
            removed_files=result.get("removed_files", []),
        ).model_dump()
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to restore translation for task: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/backups/{backup_id}/restore")
async def restore_translation_by_backup(
    backup_id: int,
    db: Session = Depends(get_db),
):
    try:
        result = await apply_service.restore_translation(db=db, backup_id=backup_id)
        data = RestoreResponse(
            restored_files=result.get("restored_files", []),
            removed_files=result.get("removed_files", []),
        ).model_dump()
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to restore translation by backup: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/backups")
async def list_backups(
    modpack_version_id: int | None = Query(None),
    db: Session = Depends(get_db),
):
    try:
        result = await apply_service.list_backups(db=db, modpack_version_id=modpack_version_id)
        backup_list = [
            BackupRecordResponse(**apply_service.serialize_backup_record(record)).model_dump()
            for record in result
        ]
        return {
            "code": 0,
            "data": backup_list,
            "message": "ok",
        }
    except Exception as e:
        logger.error("Failed to list backups: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/backups/{backup_id}")
async def delete_backup(
    backup_id: int,
    db: Session = Depends(get_db),
):
    try:
        await apply_service.delete_backup(db=db, backup_id=backup_id)
        return {
            "code": 0,
            "data": None,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to delete backup: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/generate-resourcepack")
async def generate_resourcepack(
    task_id: int,
    config: ResourcePackConfig = ResourcePackConfig(),
    db: Session = Depends(get_db),
):
    """生成汉化资源包 zip 文件。"""
    try:
        result = resourcepack_service.generate(
            db=db,
            task_id=task_id,
            config=config.model_dump(),
        )
        return {
            "code": 0,
            "data": _build_resourcepack_response(task_id, result),
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to generate resourcepack: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/{task_id}/generate-patch")
async def generate_patch_package(
    task_id: int,
    config: PatchPackageConfig = PatchPackageConfig(),
    db: Session = Depends(get_db),
):
    try:
        result = await apply_service.generate_patch_package(
            db=db,
            task_id=task_id,
            config=config.model_dump(),
        )
        data = GeneratePatchPackageResponse(**result).model_dump()
        return {
            "code": 0,
            "data": data,
            "message": "ok",
        }
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to generate patch package: %s", e)
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/{task_id}/download-resourcepack")
async def download_resourcepack(
    task_id: int,
    db: Session = Depends(get_db),
):
    """下载生成的资源包文件。"""
    try:
        result = resourcepack_service.get_cached_result(task_id)
        if not result:
            result = resourcepack_service.generate(
                db=db,
                task_id=task_id,
                config={},
            )

        file_path = result.get("file_path", "")
        filename = result.get("filename", "resourcepack.zip")

        if not file_path or not os.path.isfile(file_path):
            raise HTTPException(status_code=404, detail="Resourcepack file not found")

        return FileResponse(
            path=file_path,
            filename=filename,
            media_type="application/zip",
        )
    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except Exception as e:
        logger.error("Failed to download resourcepack: %s", e)
        raise HTTPException(status_code=500, detail=str(e))
