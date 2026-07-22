"""
GitLab client — скачивает весь репозиторий архивом и извлекает .conf файлы.

Один HTTP-запрос на проект вместо N запросов по файлу.
nginx.conf в корне репозитория игнорируется (конфиг самого nginx, не виртуальные хосты).

Config options:
  gitlab_url         - GitLab base URL
  gitlab_token       - personal access token (scope: read_api)
  gitlab_projects    - list of project paths, e.g. ['group/repo1', 'group/repo2']
  gitlab_verify_ssl  - verify SSL certificate (default: True)
"""

import io
import logging
import tarfile
from urllib.parse import quote

import requests

logger = logging.getLogger('netbox.plugins.netbox_obudozer')


def get_plugin_config():
    from django.conf import settings
    return settings.PLUGINS_CONFIG.get('netbox_obudozer', {})


def fetch_nginx_configs():
    """
    Скачивает каждый проект как tar.gz архив и извлекает все .conf файлы.

    Returns:
        tuple: (
            configs: list of (content: str, file_path: str, project_path: str),
            project_reports: list of dicts с per-project статусом
        )

    Raises:
        ValueError: если не настроены обязательные параметры
    """
    config = get_plugin_config()
    gitlab_url = config.get('gitlab_url', '').rstrip('/')
    gitlab_token = config.get('gitlab_token', '')
    projects = config.get('gitlab_projects', [])
    verify_ssl = config.get('gitlab_verify_ssl', True)

    if not gitlab_url:
        raise ValueError('gitlab_url не настроен в PLUGINS_CONFIG')
    if not gitlab_token:
        raise ValueError('gitlab_token не настроен в PLUGINS_CONFIG')
    if not projects:
        raise ValueError('gitlab_projects не настроен в PLUGINS_CONFIG')

    session = requests.Session()
    session.headers.update({'PRIVATE-TOKEN': gitlab_token})
    session.verify = verify_ssl

    all_configs = []
    project_reports = []

    for project_path in projects:
        report = {
            'project': project_path,
            'files_found': 0,
            'files_skipped': 0,
            'files_fetched': 0,
            'file_errors': [],
            'error': None,
        }
        logger.info('GitLab: downloading archive for %s', project_path)
        try:
            configs = _fetch_project_archive(session, gitlab_url, project_path)
            report['files_fetched'] = len(configs)
            report['files_found'] = len(configs)
            all_configs.extend(configs)
            logger.info('GitLab: extracted %d .conf files from %s', len(configs), project_path)
        except Exception as e:
            report['error'] = str(e)
            logger.error('GitLab: failed to fetch archive for %s — %s', project_path, e)

        project_reports.append(report)

    logger.info('GitLab: total %d .conf files from %d projects', len(all_configs), len(projects))
    return all_configs, project_reports


def _fetch_project_archive(session, gitlab_url, project_path):
    """
    Скачивает весь проект как tar.gz и возвращает список (content, path, project).
    Пропускает nginx.conf в корне репозитория.
    """
    project_id = quote(project_path, safe='')
    url = f'{gitlab_url}/api/v4/projects/{project_id}/repository/archive.tar.gz'

    resp = session.get(url, params={'ref': 'HEAD'}, timeout=120)
    resp.raise_for_status()

    configs = []

    with tarfile.open(fileobj=io.BytesIO(resp.content), mode='r:gz') as tar:
        for member in tar.getmembers():
            if not member.isfile():
                continue
            if not member.name.endswith('.conf'):
                continue

            # Путь в архиве: "{project}-{sha}/path/to/file.conf"
            # Убираем первый компонент (префикс архива)
            parts = member.name.split('/', 1)
            relative_path = parts[1] if len(parts) == 2 else member.name

            # Игнорируем nginx.conf в корне (конфиг самого nginx)
            if relative_path == 'nginx.conf':
                logger.debug('GitLab: skipping root nginx.conf in %s', project_path)
                continue

            f = tar.extractfile(member)
            if f is None:
                continue

            raw = f.read()
            try:
                content = raw.decode('utf-8')
            except UnicodeDecodeError:
                content = raw.decode('latin-1')

            configs.append((content, relative_path, project_path))

    return configs
