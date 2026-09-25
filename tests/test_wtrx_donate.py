"""Offline donation defaults, preserving the site's template presentation (#4/#14)."""

from types import SimpleNamespace

import pytest
from django.utils import translation
from wtrx.blocks import DonateBlock

from tests.test_golden import assert_matches_golden
from wagtail_markdown_agents.rendering import render_block
from wagtail_markdown_agents.rendering.registry import BlockRenderError


@pytest.fixture
def context():
    return {
        "site": SimpleNamespace(hostname="example.org"),
        "settings": {
            "wtrx": {
                "IntegrationSettings": SimpleNamespace(
                    get_integration_config=lambda slug: (
                        {
                            "base_url": "https://donate.example.org/campaign",
                            "suggested_amounts": "10,25",
                        }
                        if slug == "actblue"
                        else None
                    )
                )
            }
        },
    }


def render(context, **overrides):
    block = DonateBlock()
    value = block.to_python(
        {"content": "<h2>Support the campaign</h2>", "override_amounts": [], **overrides}
    )
    return render_block(block, value, context)


def test_donation_defaults_and_overrides_golden(context):
    outputs = [
        "# Site defaults\n\n" + render(context),
        "# Authored overrides\n\n"
        + render(
            context,
            override_url="https://donate.example.org/local",
            override_amounts=["5", "15"],
            button_text="Give locally",
        ),
        "# No integration\n\n" + render({}),
    ]
    assert_matches_golden("wtrx-donate.md", "\n\n".join(outputs))
    assert "[Donate](https://donate.example.org/campaign)" in outputs[0]
    assert "?amount=25" in outputs[0]
    assert "campaign" not in outputs[1].split("\n\n", 2)[-1]
    assert outputs[2] == "# No integration\n\n## Support the campaign"


@pytest.mark.parametrize("amounts", ["", "not-a-number", "10,broken", None])
def test_invalid_default_amounts_keep_the_donation_destination(context, amounts):
    context["settings"]["wtrx"]["IntegrationSettings"].get_integration_config = lambda slug: {
        "base_url": "https://donate.example.org/campaign",
        "suggested_amounts": amounts,
    }
    assert render(context) == (
        "## Support the campaign\n\n[Donate](https://donate.example.org/campaign)"
    )


def test_disabled_integration_and_missing_site_do_not_use_defaults(context):
    assert render({"settings": context["settings"]}) == "## Support the campaign"
    context["settings"]["wtrx"]["IntegrationSettings"].get_integration_config = lambda slug: None
    assert render(context) == "## Support the campaign"
    assert "[Give](https://donate.example.org/override)" in render(
        {}, override_url="https://donate.example.org/override", button_text="Give"
    )


def test_donation_uses_template_language_and_does_not_mutate_context(context):
    keys = set(context)
    with translation.override("fr"):
        output = render(context, override_amounts=["12.50"], button_text="Contribuer")
    assert "$12,50" in output
    assert "[Contribuer]" in output
    assert set(context) == keys


def test_donation_template_failure_is_explicit(context):
    block = DonateBlock(template="missing-donation-template.html")
    with pytest.raises(BlockRenderError, match="DonateBlock"):
        render_block(block, block.to_python({"override_amounts": []}), context)
