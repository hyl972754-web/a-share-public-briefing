"""Fail-closed publication gate; public access alone is never reuse permission."""
from datetime import date
from urllib.parse import urlsplit


def allowed(source, url):
    rights = source.get('public_reuse', {})
    try:
        date.fromisoformat(rights['checked_on'])
        parsed = urlsplit(url)
        basis = urlsplit(rights['basis_url'])
        return bool(rights.get('decision') == 'allowed' and basis.scheme == 'https' and basis.hostname
                    and parsed.scheme == 'https' and not parsed.username and not parsed.password
                    and parsed.hostname in source.get('allowed_hosts', [])
                    and any(parsed.path.startswith(p) for p in rights.get('allowed_article_prefixes', [])))
    except (ValueError, KeyError, TypeError):
        return False


def publishable(report):
    if report.get('is_demo') or not report.get('items'):
        return False
    sources = {s['id']: s for s in report.get('sources', [])}
    for item in report['items']:
        source = sources.get(item.get('source_id'), {})
        if not allowed(source, item.get('url', '')):
            return False
        if item.get('license_basis_url') != source['public_reuse']['basis_url']:
            return False
        if item.get('summary_method') != 'independent_metadata_analysis_v1':
            return False
        if any(k in item for k in ('body', 'description', 'full_text')):
            return False
    return True
