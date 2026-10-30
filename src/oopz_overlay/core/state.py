"""Application transitions; drafts stay in memory, scoped to account and channel."""
from dataclasses import dataclass, field, replace
from .settings import AppSettings
DraftKey = tuple[str, str, str]

@dataclass(frozen=True, slots=True)
class AppState:
    settings: AppSettings = field(default_factory=AppSettings)
    mode: str = 'passive'
    visible: bool = True
    connected: bool = False
    generation: int = 0
    status: str = 'starting'
    drafts: dict[DraftKey, str] = field(default_factory=dict)

    @property
    def key(self) -> DraftKey:
        s = self.settings
        return (s.person_uid, s.area_id, s.channel_id)

    @property
    def draft(self) -> str:
        return self.drafts.get(self.key, '')

def reduce(state: AppState, action: str, value=None, *, generation=None) -> AppState:
    if generation is not None and generation != state.generation:
        return state
    if action == 'settings':
        return replace(state, settings=value)
    if action == 'activate':
        return replace(state, visible=True, mode='input' if state.settings.channel_id else 'picker')
    if action == 'picker':
        return replace(state, mode='picker')
    if action == 'input':
        return replace(state, mode='input')
    if action == 'cancel':
        return replace(state, mode='passive')
    if action == 'toggle':
        return replace(state, visible=not state.visible, mode='passive')
    if action == 'draft':
        return replace(state, drafts={**state.drafts, state.key: value})
    if action == 'submit':
        return replace(state, mode='passive', drafts={**state.drafts, state.key: ''})
    if action == 'send_failed':
        key, text = value
        previous = state.drafts.get(key, '')
        draft = '\n'.join((part for part in (previous, text) if part))
        return replace(state, drafts={**state.drafts, key: draft})
    if action == 'connected':
        return replace(state, connected=value, status='connected' if value else 'reconnecting')
    if action == 'connection':
        return replace(state, connected=False, generation=value, status='connecting')
    if action == 'logout':
        return replace(state, connected=False, status='login', generation=value, settings=replace(state.settings, person_uid='', jwt_token='', device_id=''))
    if action == 'status':
        return replace(state, status=value)
    raise ValueError(f'Unknown action: {action}')
