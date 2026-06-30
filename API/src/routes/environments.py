"""Platform environments API (Screen A) and local dataset upload."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from fastapi import APIRouter, File, Header, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from DE.src.datasets.job_cluster_metrics_csv import (
    LOCAL_DATASET_KEY,
    STORED_FILENAME,
    TEMPLATE_DOWNLOAD_NAME,
    get_template_csv_bytes,
    validate_upload_content,
)
from shared.auth.admin import is_admin
from shared.services.environment_connection_service import EnvironmentConnectionService
from shared.services.environment_dataset_service import EnvironmentDatasetService
from shared.services.environment_service import environment_readiness
from shared.services.local_dataset_service import (
    clear_upload,
    get_dataset_info,
    resolve_fallback_path,
    save_upload,
)
from shared.services.platform_environment_service import (
    get_environment,
    list_environments,
    update_environment,
)
from shared.utils.logging import get_logger

router = APIRouter()
logger = get_logger(__name__)

_LOCAL_FALLBACK = str(resolve_fallback_path())


def _user_id(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    return (x_user_id or x_user_name or "anonymous").strip() or "anonymous"


def _require_admin(x_user_name: Optional[str], x_user_id: Optional[str]) -> str:
    user = _user_id(x_user_name, x_user_id)
    if not is_admin(user):
        raise HTTPException(status_code=403, detail="Admin access required")
    return user


def _local_dataset_info(user: str) -> Dict[str, Any]:
    return get_dataset_info(
        user,
        dataset_key=LOCAL_DATASET_KEY,
        stored_filename=STORED_FILENAME,
        fallback_path=_LOCAL_FALLBACK,
    )


_conn_svc = EnvironmentConnectionService()
_dataset_svc = EnvironmentDatasetService()


def _env_payload(env, user: str, *, admin_view: bool = False) -> Dict[str, Any]:
    readiness = environment_readiness(
        env.id,
        user,
        local_fallback_path=_LOCAL_FALLBACK,
        local_dataset_key=LOCAL_DATASET_KEY,
        local_stored_filename=STORED_FILENAME,
    )
    local_dataset = _local_dataset_info(user) if env.source_type == "local_csv" else None
    metrics_count = len(_conn_svc.list_connections(environment_id=env.id, purpose="metrics"))
    connection_count = len(_conn_svc.list_connections(environment_id=env.id))
    dataset_count = len(_dataset_svc.list_datasets(environment_id=env.id))
    default_ds = _dataset_svc.get_default_dataset(env.id)
    return env.to_dict(
        readiness=readiness,
        local_dataset=local_dataset,
        is_admin=admin_view,
        connection_count=connection_count,
        metrics_connection_count=metrics_count,
        metrics_dataset_count=dataset_count,
        default_dataset_name=default_ds.name if default_ds else None,
        default_dataset_ref=default_ds.table_ref if default_ds else None,
    )


class EnvironmentUpdateRequest(BaseModel):
    display_name: Optional[str] = Field(default=None, min_length=1)
    description: Optional[str] = None
    environment_tier: Optional[str] = Field(default=None, min_length=1)
    sort_order: Optional[int] = None
    icon: Optional[str] = None
    is_enabled: Optional[bool] = None


@router.get("")
def list_platform_environments(
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> List[Dict[str, Any]]:
    """List platform environments for Screen A (from Postgres)."""
    user = _user_id(x_user_name, x_user_id)
    admin_view = is_admin(user)
    try:
        return [_env_payload(env, user, admin_view=admin_view) for env in list_environments()]
    except Exception as e:
        logger.error("list_platform_environments_failed", error=str(e))
        raise HTTPException(
            status_code=503,
            detail=f"Unable to load environments: {e}",
        ) from e


@router.get("/local/template")
def download_local_template() -> Response:
    """Download CSV template for job cluster metrics (current jobs browse agent)."""
    return Response(
        content=get_template_csv_bytes(),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{TEMPLATE_DOWNLOAD_NAME}"'},
    )


@router.get("/local/dataset")
def get_local_dataset(
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    return _local_dataset_info(_user_id(x_user_name, x_user_id))


@router.post("/local/upload")
async def upload_local_dataset(
    file: UploadFile = File(...),
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    user = _user_id(x_user_name, x_user_id)
    if not file.filename or not file.filename.lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="Upload a .csv file.")
    content = await file.read()
    if not content:
        raise HTTPException(status_code=400, detail="File is empty.")
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File exceeds 50 MB limit.")
    try:
        info = save_upload(
            user,
            file.filename,
            content,
            dataset_key=LOCAL_DATASET_KEY,
            stored_filename=STORED_FILENAME,
            validator=validate_upload_content,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e
    logger.info("local_csv_uploaded", user=user, filename=file.filename)
    return info


@router.delete("/local/dataset")
def reset_local_dataset(
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    user = _user_id(x_user_name, x_user_id)
    return clear_upload(
        user,
        dataset_key=LOCAL_DATASET_KEY,
        stored_filename=STORED_FILENAME,
        fallback_path=_LOCAL_FALLBACK,
    )


@router.get("/{environment_id}")
def get_platform_environment(
    environment_id: str,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    env = get_environment(environment_id)
    if not env:
        raise HTTPException(status_code=404, detail="Environment not found")
    user = _user_id(x_user_name, x_user_id)
    return _env_payload(env, user, admin_view=is_admin(user))


@router.put("/{environment_id}")
def update_platform_environment(
    environment_id: str,
    body: EnvironmentUpdateRequest,
    x_user_name: Optional[str] = Header(default=None),
    x_user_id: Optional[str] = Header(default=None),
) -> Dict[str, Any]:
    """Admin: update environment configuration stored in Postgres."""
    user = _require_admin(x_user_name, x_user_id)
    patch = body.model_dump(exclude_unset=True)
    if not patch:
        raise HTTPException(status_code=400, detail="No fields to update")
    try:
        env = update_environment(environment_id, patch)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    logger.info("platform_environment_updated", environment_id=environment_id, user=user)
    return _env_payload(env, user, admin_view=True)
