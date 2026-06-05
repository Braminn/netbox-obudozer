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
        list of (content: str, file_path: str, project_path: str)

    Raises:
        ValueError: if required settings are missing
    """
    config = get_plugin_config()
    gitlab_url = config.get('gitlab_url', '').rstrip('/')
    gitlab_token = config.get('gitlab_token', '')
    projects = config.get('gitlab_projects', [])
    nginx_path = config.get('gitlab_nginx_path', 'sites-enabled')
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

    for project_path in projects:
        logger.info('GitLab: fetching .conf files from %s/%s', project_path, nginx_path)
        try:
            files = _list_conf_files(session, gitlab_url, project_path, nginx_path)
            logger.info('GitLab: found %d .conf files in %s', len(files), project_path)

            for file_path in files:
                try:
                    content = _get_file_content(session, gitlab_url, project_path, file_path)
                    all_configs.append((content, file_path, project_path))
                except Exception as e:
                    logger.warning('GitLab: skipping %s — %s', file_path, e)

        except Exception as e:
            logger.error('GitLab: failed to process project %s — %s', project_path, e)

    logger.info('GitLab: fetched %d .conf files total', len(all_configs))
    return all_configs


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
