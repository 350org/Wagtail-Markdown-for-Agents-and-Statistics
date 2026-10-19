"""Site profile for 350.org's Wagtail site (``350org/wagtail-wtr-350``, app ``wtrx``).

Turn it on in that site's settings::

    WAGTAIL_MARKDOWN_AGENTS = {"PROFILE": "wagtail_markdown_agents.profiles.wtrx"}

The modules import the site's ``wtrx`` app, so the profile only works on that
site. Another site should copy this folder and change it; see
docs/site-profiles.md. ``blocks.json`` is the block snapshot that
``scripts/profile_drift.py`` compares the site against.
"""
