from typing import Annotated

from fastapi import Depends, Request

from ..cloud.registry import CloudRegistry
from ..core.config import Settings
from ..core.security import get_current_user_id
from ..repositories.store import Store


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


def get_cloud(request: Request) -> CloudRegistry:
    return request.app.state.cloud


def get_store(request: Request) -> Store:
    return request.app.state.store


SettingsDep = Annotated[Settings, Depends(get_settings)]
CloudDep = Annotated[CloudRegistry, Depends(get_cloud)]
StoreDep = Annotated[Store, Depends(get_store)]
UserIdDep = Annotated[str, Depends(get_current_user_id)]