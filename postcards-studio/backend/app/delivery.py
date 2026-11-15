"""Select one delivery destination. NAS takes precedence over legacy Yandex."""
from .webdav import NasWebDAVDelivery
from .yandex_disk import YandexDiskApiDelivery, YandexDiskDelivery, YandexDiskDeliveryError

DeliveryError = YandexDiskDeliveryError


def create_delivery(cfg):
    if cfg.nas_delivery_enabled:
        return NasWebDAVDelivery(cfg.nas_webdav_url, cfg.nas_username, cfg.nas_password, cfg.nas_path)
    if cfg.yandex_delivery_enabled:
        if cfg.yandex_disk_oauth_token:
            return YandexDiskApiDelivery(cfg.yandex_disk_api_url, cfg.yandex_disk_oauth_token, cfg.yandex_disk_path)
        return YandexDiskDelivery(cfg.yandex_webdav_url, cfg.yandex_disk_username,
                                  cfg.yandex_disk_app_password, cfg.yandex_disk_path)
    return None
