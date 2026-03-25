from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import tomllib


@dataclass(slots=True)
class ProfilesConfig:
    local: str = "local"
    cloud: str = "cloud"


@dataclass(slots=True)
class DatabaseConfig:
    path: str = ".codex-adv/memory.db"


@dataclass(slots=True)
class RoutingConfig:
    simple_complexity_threshold: int = 3
    prefer_local_task_types: tuple[str, ...] = (
        "explain",
        "single_file_edit",
        "small_fix",
        "test_help",
    )
    cloud_task_types: tuple[str, ...] = (
        "multi_file_edit",
        "architecture",
        "large_refactor",
        "unknown",
    )
    min_local_success_rate: float = 0.7


@dataclass(slots=True)
class FallbackConfig:
    enabled: bool = True
    max_attempts: int = 2
    failure_markers: tuple[str, ...] = (
        "I cannot",
        "TODO",
        "not implemented",
        "insufficient context",
    )
    min_output_chars: int = 120


@dataclass(slots=True)
class RewriteStyleConfig:
    style: str = "compress"


@dataclass(slots=True)
class RewritesConfig:
    local: RewriteStyleConfig
    cloud: RewriteStyleConfig


@dataclass(slots=True)
class AppConfig:
    profiles: ProfilesConfig
    database: DatabaseConfig
    routing: RoutingConfig
    fallback: FallbackConfig
    rewrites: RewritesConfig


DEFAULT_CONFIG = AppConfig(
    profiles=ProfilesConfig(),
    database=DatabaseConfig(),
    routing=RoutingConfig(),
    fallback=FallbackConfig(),
    rewrites=RewritesConfig(
        local=RewriteStyleConfig(style="compress"),
        cloud=RewriteStyleConfig(style="structure"),
    ),
)


def _tuple(value: object, default: tuple[str, ...]) -> tuple[str, ...]:
    if isinstance(value, list):
        return tuple(str(item) for item in value)
    return default


def load_config(config_path: str | Path | None) -> AppConfig:
    if config_path is None:
        path = Path(".codex-adv/router.toml")
    else:
        path = Path(config_path)

    if not path.exists():
        return DEFAULT_CONFIG

    data = tomllib.loads(path.read_text())

    profiles_data = data.get("profiles", {})
    database_data = data.get("database", {})
    routing_data = data.get("routing", {})
    fallback_data = data.get("fallback", {})
    rewrites_data = data.get("rewrites", {})
    rewrites_local = rewrites_data.get("local", {})
    rewrites_cloud = rewrites_data.get("cloud", {})

    return AppConfig(
        profiles=ProfilesConfig(
            local=str(profiles_data.get("local", DEFAULT_CONFIG.profiles.local)),
            cloud=str(profiles_data.get("cloud", DEFAULT_CONFIG.profiles.cloud)),
        ),
        database=DatabaseConfig(
            path=str(database_data.get("path", DEFAULT_CONFIG.database.path))
        ),
        routing=RoutingConfig(
            simple_complexity_threshold=int(
                routing_data.get(
                    "simple_complexity_threshold",
                    DEFAULT_CONFIG.routing.simple_complexity_threshold,
                )
            ),
            prefer_local_task_types=_tuple(
                routing_data.get("prefer_local_task_types"),
                DEFAULT_CONFIG.routing.prefer_local_task_types,
            ),
            cloud_task_types=_tuple(
                routing_data.get("cloud_task_types"),
                DEFAULT_CONFIG.routing.cloud_task_types,
            ),
            min_local_success_rate=float(
                routing_data.get(
                    "min_local_success_rate",
                    DEFAULT_CONFIG.routing.min_local_success_rate,
                )
            ),
        ),
        fallback=FallbackConfig(
            enabled=bool(
                fallback_data.get("enabled", DEFAULT_CONFIG.fallback.enabled)
            ),
            max_attempts=int(
                fallback_data.get("max_attempts", DEFAULT_CONFIG.fallback.max_attempts)
            ),
            failure_markers=_tuple(
                fallback_data.get("failure_markers"),
                DEFAULT_CONFIG.fallback.failure_markers,
            ),
            min_output_chars=int(
                fallback_data.get(
                    "min_output_chars", DEFAULT_CONFIG.fallback.min_output_chars
                )
            ),
        ),
        rewrites=RewritesConfig(
            local=RewriteStyleConfig(
                style=str(
                    rewrites_local.get("style", DEFAULT_CONFIG.rewrites.local.style)
                )
            ),
            cloud=RewriteStyleConfig(
                style=str(
                    rewrites_cloud.get("style", DEFAULT_CONFIG.rewrites.cloud.style)
                )
            ),
        ),
    )
