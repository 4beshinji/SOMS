from providers.slack import SlackProvider
from providers.github import GitHubProvider

PROVIDERS = {
    "slack": SlackProvider,
    "github": GitHubProvider,
}


def get_provider(name: str):
    cls = PROVIDERS.get(name)
    if not cls:
        raise ValueError(f"Unknown provider: {name}")
    return cls()
