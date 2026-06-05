"""
GitLab client — fetches nginx .conf files from configured repositories.
Mirrors the structure of vmware.py: thin API wrapper, no business logic.

Config options:
  gitlab_url          - GitLab base URL
  gitlab_token        - personal access token (scope: read_api)
  gitlab_projects     - list of project paths, e.g. ['group/repo1', 'group/repo2']
  gitlab_nginx_path   - subfolder to search in each project (default: 'sites-enabled')
  gitlab_verify_ssl   - verify SSL certificate (default: True)
"""

import logging
from urllib.parse import quote

import requests

logger = logging.getLogger('netbox.plugins.netbox_obudozer')


def get_plugin_config():
    from django.conf import settings
    return settings.PLUGINS_CONFIG.get('netbox_obudozer', {})


def fetch_nginx_configs():
    """
    Fetch all *.conf files from every project listed in gitlab_projects.

    Returns:
        tuple: (
            configs: list of (content: str, file_path: str, project_path: str),
            project_reports: list of dicts with per-project status
        )

    Raises:
        ValueError: if required settings are missing
    """
    config = get_plugin_config()
    gitlab_url = config.get('gitlab_url', '').rstrip('/')
    gitlab_token = config.get('gitlab_token', '')
    projects = config.get('gitlab_projects', [])
    nginx_path_cfg = config.get('gitlab_nginx_path', ['sites-enabled', 'sites-available'])
    # Нормализуем: строка → список
    nginx_paths = [nginx_path_cfg] if isinstance(nginx_path_cfg, str) else list(nginx_path_cfg)
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
            'nginx_path': ', '.join(nginx_paths),
            'files_found': 0,
            'files_fetched': 0,
            'file_errors': [],
            'error': None,
        }
        logger.info('GitLab: fetching .conf files from %s in %s', nginx_paths, project_path)
        try:
            # Собираем файлы из всех папок, без дублей
            # Ошибка для одной папки (например 404) не прерывает перебор остальных
            seen_paths = set()
            files = []
            for nginx_path in nginx_paths:
                try:
                    for f in _list_conf_files(session, gitlab_url, project_path, nginx_path):
                        if f not in seen_paths:
                            seen_paths.add(f)
                            files.append(f)
                except Exception as e:
                    logger.debug('GitLab: %s/%s — %s', project_path, nginx_path, e)
            report['files_found'] = len(files)
            logger.info('GitLab: found %d .conf files in %s', len(files), project_path)

            for file_path in files:
                try:
                    content = _get_file_content(session, gitlab_url, project_path, file_path)
                    all_configs.append((content, file_path, project_path))
                    report['files_fetched'] += 1
                except Exception as e:
                    msg = f'{file_path}: {e}'
                    report['file_errors'].append(msg)
                    logger.warning('GitLab: skipping %s — %s', file_path, e)

        except Exception as e:
            report['error'] = str(e)
            logger.error('GitLab: failed to process project %s — %s', project_path, e)

        project_reports.append(report)

    logger.info('GitLab: fetched %d .conf files total', len(all_configs))
    return all_configs, project_reports


def _list_conf_files(session, gitlab_url, project_path, nginx_path):
    """
    Return list of .conf file paths inside nginx_path in the project.
    Uses GitLab Repository Tree API with pagination.
    """
    project_id = quote(project_path, safe='')
    url = f'{gitlab_url}/api/v4/projects/{project_id}/repository/tree'

    conf_files = []
    page = 1

    while True:
        resp = session.get(url, params={
            'path': nginx_path,
            'recursive': 'true',
            'per_page': 100,
            'page': page,
            'ref': 'HEAD',  # resolves to the project's default branch
        }, timeout=30)
        resp.raise_for_status()

        items = resp.json()
        if not items:
            break

        for item in items:
            if item.get('type') == 'blob' and item.get('name', '').endswith('.conf'):
                conf_files.append(item['path'])

        # GitLab returns X-Next-Page header when there are more pages
        next_page = resp.headers.get('X-Next-Page', '')
        if not next_page:
            break
        page = int(next_page)

    return conf_files


def _get_file_content(session, gitlab_url, project_path, file_path):
    """Return raw text content of a file at HEAD."""
    project_id = quote(project_path, safe='')
    file_path_encoded = quote(file_path, safe='')
    url = f'{gitlab_url}/api/v4/projects/{project_id}/repository/files/{file_path_encoded}/raw'

    resp = session.get(url, params={'ref': 'HEAD'}, timeout=30)
    resp.raise_for_status()

    # GitLab returns bytes; decode as UTF-8 with fallback to latin-1
    # Punycode/cyrillic domain names in server_name are ASCII-safe,
    # but file content (comments etc.) may contain Cyrillic text
    try:
        return resp.content.decode('utf-8')
    except UnicodeDecodeError:
        return resp.content.decode('latin-1')
