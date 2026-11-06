from ..core.config import Settings
from .base import ServiceStatus
from .codearts import CodeArtsService
from .dcs import DcsService
from .kms import KmsService
from .obs import ObsService
from .rds import RdsService


class CloudRegistry:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.rds = RdsService(settings)
        self.redis = DcsService(settings)
        self.codearts = CodeArtsService(settings)
        self.obs = ObsService(settings)
        self.kms = KmsService(settings)

    @property
    def services(self) -> tuple:
        return (self.rds, self.redis, self.codearts, self.obs, self.kms)

    async def check_all(self) -> list[ServiceStatus]:
        return [await service.check() for service in self.services]

    async def close(self) -> None:
        for service in self.services:
            await service.close()


def build_registry(settings: Settings) -> CloudRegistry:
    return CloudRegistry(settings)