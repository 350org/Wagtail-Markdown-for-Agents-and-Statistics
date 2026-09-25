"""Markdown renderers for the 350.org Wagtail site's blocks (``wtrx``, #14).

Add ``"wagtail_markdown_agents.contrib.wtrx"`` to ``INSTALLED_APPS`` after
``"wagtail_markdown_agents"``. The renderers are registered through the public
custom-block mechanism (#18), like any project's, and import ``wtrx.blocks``,
so this app only works alongside the site's ``wtrx`` app. The block contracts
are the matrix agreed on #14, against ``wagtail-wtr-350`` ``improvements`` at
1997766.
"""
