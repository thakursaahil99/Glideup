"""All available job source plugins. Adding a source = one module + one line here."""

from app.jobsources.base import JobSourcePlugin
from app.jobsources.plugins.adzuna import AdzunaPlugin
from app.jobsources.plugins.ats import AshbyPlugin, GreenhousePlugin, LeverPlugin

PLUGINS: dict[str, JobSourcePlugin] = {
    plugin.key: plugin
    for plugin in (GreenhousePlugin(), LeverPlugin(), AshbyPlugin(), AdzunaPlugin())
}

# Sources that are disabled until an admin turns them on (e.g. they need an API key).
DISABLED_BY_DEFAULT = {"adzuna"}


def get_plugin(key: str) -> JobSourcePlugin:
    try:
        return PLUGINS[key]
    except KeyError as exc:
        raise KeyError(f"No job source plugin named '{key}'") from exc
