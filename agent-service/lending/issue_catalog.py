"""Compact, project-scoped Redmine context for planning and duplicate detection."""
import re
import unicodedata
from urllib.parse import urlencode


def folded(text):
    text = unicodedata.normalize('NFD', text.casefold().replace('đ', 'd'))
    return ''.join(c for c in text if unicodedata.category(c) != 'Mn')


def project_issues(api, project):
    issues = []
    offset = 0
    while True:
        page = api.request('GET', '/issues.json?' + urlencode({
            'project_id': project, 'status_id': '*', 'limit': 100, 'offset': offset,
            'sort': 'id:desc',
        }))
        rows = page['issues']
        issues.extend(row for row in rows if row['project']['id'] == project)
        offset += len(rows)
        if not rows or offset >= page['total_count']:
            return issues


def compact(issue):
    return {
        'id': issue['id'], 'title': issue['subject'],
        'parent_id': issue.get('parent', {}).get('id'),
        'tracker': issue['tracker']['name'], 'tracker_id': issue['tracker']['id'],
        'status': issue['status']['name'], 'closed': issue['status'].get('is_closed', False),
        'assignee': issue.get('assigned_to', {}).get('name'),
    }


def planning_catalog(issues, message):
    """Show all story titles and the best matching tasks, including closed work."""
    tokens = set(re.findall(r'[a-z0-9]+', folded(message)))
    tokens -= {'toi','ban','cai','thi','cho','them','task','story','sua','di','la','va','cua','mot','nay','no','duoc'}
    explicit = {int(value) for value in re.findall(r'(?:#|story\s*|task\s*)(\d+)', folded(message))}
    def score(issue):
        text = folded(issue['subject'] + ' ' + (issue.get('description') or ''))
        return (100 if issue['id'] in explicit or issue.get('parent',{}).get('id') in explicit else 0) + sum(
            token in text for token in tokens)
    matches = sorted((issue for issue in issues if score(issue)), key=score, reverse=True)[:24]
    return {
        'stories': [compact(issue) for issue in issues if issue['tracker']['id'] == 4],
        'matching_issues': [{**compact(issue), 'description': (issue.get('description') or '')[:1000]}
                            for issue in matches],
        'total_issues': len(issues),
    }
