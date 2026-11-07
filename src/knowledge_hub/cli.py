"""Local entry points and portable application-data configuration."""
import os
import secrets
from pathlib import Path
from platformdirs import user_data_dir


def resolve_data_dir(data_dir: Path | None = None) -> Path:
    if data_dir is not None:
        return Path(data_dir).expanduser().resolve()
    configured = os.environ.get('KNOWLEDGE_HUB_DATA_DIR')
    return Path(configured).expanduser().resolve() if configured else Path(user_data_dir('Knowledge Hub', appauthor=False))


def load_agent_token(data_dir: Path) -> str:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = data_dir / 'agent.token'
    try:
        descriptor = os.open(target, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError:
        if target.is_symlink():
            raise ValueError('Agent token must not be a symbolic link')
        target.chmod(0o600)
        token = target.read_text()
        if len(token) < 32:
            raise ValueError('Invalid agent token file')
        return token
    token = secrets.token_urlsafe(32)
    with os.fdopen(descriptor, 'w') as stream:
        stream.write(token)
    return token


def main(argv: list[str] | None = None):
    import multiprocessing
    multiprocessing.freeze_support()
    import argparse
    import sys
    supplied = list(sys.argv[1:] if argv is None else argv)
    if supplied[:1] == ['--capture-extractor-worker']:
        if len(supplied) != 2 or supplied[1] not in {'application/pdf', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'}:
            raise SystemExit(2)
        from .intake_extractors import worker_main
        return worker_main(supplied[1])
    parser = argparse.ArgumentParser(prog='knowledge-hub')
    parser.add_argument('command', choices=['mcp', 'desktop', 'serve'], nargs='?', default='desktop')
    parser.add_argument('--data-dir', type=Path)
    parser.add_argument('--port', type=int, default=8765)
    arguments = parser.parse_args(argv)
    if arguments.command == 'serve':
        import uvicorn
        from .http import create_app
        directory = resolve_data_dir(arguments.data_dir)
        human = os.environ.get('KNOWLEDGE_HUB_HUMAN_TOKEN') or secrets.token_urlsafe(32)
        app = create_app(directory, human, load_agent_token(directory))
        return uvicorn.run(app, host='127.0.0.1', port=arguments.port, access_log=False, log_level='warning')
    if arguments.command == 'desktop':
        from .desktop import launch
        return launch(data_dir=resolve_data_dir(arguments.data_dir))
    from .mcp import create_mcp
    create_mcp(resolve_data_dir(arguments.data_dir)).run(transport='stdio')


if __name__ == '__main__':
    main()

