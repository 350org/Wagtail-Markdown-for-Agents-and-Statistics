"""Stand-in for the site's ``wtrx.integrations.actionkit`` form fetch.

The real module fetches a campaign's embed form from ActionKit, caches it, and
``split_action_header`` lifts the intro (pretitle, title, description and
petition text) out of it. Tests register that intro in ``INTROS`` instead; the
"form" handed between the two functions is the intro itself. ``FETCHES``
records each fetch, so tests can check when ActionKit would be contacted.
"""

INTROS = {}
FETCHES = []


def fetch_and_cache_embed_form_html(hostname, short_form_id):
    FETCHES.append((hostname, short_form_id))
    return INTROS.get((hostname, short_form_id))


def split_action_header(html):
    return (html or None), html
