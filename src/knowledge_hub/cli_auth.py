"""Fixed official-client handoffs; no shell execution or credential-store reads."""
from pathlib import Path
import hashlib
import shlex
from .core import DomainError

PROFILE_VARIABLES = {'chatgpt': 'CODEX_HOME', 'gemini': 'GEMINI_CLI_HOME', 'hermes': 'HERMES_HOME',
                     'copilot': 'XDG_CONFIG_HOME', 'opencode': 'XDG_CONFIG_HOME'}


def profile_home(root, connection):
    if connection not in PROFILE_VARIABLES:
        raise DomainError('invalid_configuration', 422)
    directory = Path(root).absolute() / ('cli-auth' if connection in {'copilot', 'opencode'} else 'curator-clients') / connection
    # Validate before mkdir/chmod or handing this profile to an official client.
    # In particular GEMINI_CLI_HOME=config must never redirect to another account.
    paths = [directory, *directory.parents,
             *(directory / name for name in ('config', '.copilot', 'data', 'xdg-config', 'xdg-data', 'xdg-cache'))]
    if any(path.is_symlink() for path in paths):
        raise DomainError('unsafe_local_storage')
    return directory


def hermes_port(root):
    # Stable app-data-root-specific port, never the owner's default proxy port.
    return 18000 + int(hashlib.sha256(str(Path(root).resolve()).encode()).hexdigest()[:4], 16) % 10000


def auth_handoff(root, connection, executable, guide, command):
    home = profile_home(root, connection)
    home.mkdir(parents=True, exist_ok=True, mode=0o700)
    home.chmod(0o700)
    environment = {'HOME': str(home), PROFILE_VARIABLES[connection]: str(home / 'config'),
                   'XDG_CONFIG_HOME': str(home / 'xdg-config'), 'XDG_DATA_HOME': str(home / 'xdg-data'),
                   'XDG_CACHE_HOME': str(home / 'xdg-cache')}
    # The profile variable must win even when it is XDG_CONFIG_HOME.
    environment[PROFILE_VARIABLES[connection]] = str(home / 'config')
    if connection == 'copilot':
        environment['COPILOT_HOME'] = str(home / '.copilot')
    elif connection == 'opencode':
        environment['XDG_DATA_HOME'] = str(home / 'data')
    command = ['hermes', 'portal'] if connection == 'hermes' else list(command)
    import shutil
    node = shutil.which('node')
    runtime_path = '/usr/bin:/bin:/usr/local/bin:/opt/homebrew/bin' + (':' + str(Path(node).parent) if node else '')
    prefix = ['env', '-i', 'PATH=' + runtime_path,
              *[f'{key}={value}' for key, value in environment.items()]]
    actual = [executable or command[0], *command[1:]]
    steps = [prefix + actual]
    if connection == 'hermes':
        steps.append(prefix + [executable or 'hermes', 'proxy', 'start', '--provider', 'nous',
                               '--host', '127.0.0.1', '--port', str(hermes_port(root))])
    return {'status': 'human_cli_handoff' if executable else 'missing_cli',
            'command': command, 'environment': environment, 'cwd': str(home),
            'cwd_command': shlex.join(['cd', '--', str(home)]),
            'steps': steps, 'display_commands': [shlex.join(step) for step in steps],
            'install_url': guide, 'automatic_execution': False, 'readiness': 'not_checked',
            'execution': 'diagnostic_required' if connection in {'hermes', 'gemini', 'copilot', 'opencode'} else 'blocked_tool_denial_unverified',
            'reason': ('Run these commands yourself in a terminal from the displayed working directory. '
                       'Use only this app-owned profile; no existing client credentials are imported. '
                       'Sign-in is not a successful connection test and never enables processing.'
                       + (' Hermes uses only its subscription proxy (Nous), not the agent API server.'
                          if connection == 'hermes' else ''))}
