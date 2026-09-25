"""350.org block renderers in contrib.wtrx (#14), against a stand-in for wtrx.blocks."""

from types import SimpleNamespace

import pytest
from django.core.exceptions import ImproperlyConfigured
from wagtail.embeds import embeds
from wagtail.embeds.models import Embed
from wagtail.images import get_image_model
from wagtail.images.tests.utils import get_test_image_file
from wagtail.models import Page, Site
from wtrx import blocks as wtrx

from wagtail_markdown_agents.rendering import render_block, render_page
from wagtail_markdown_agents.rendering.context import render_context

YOUTUBE = "https://www.youtube.com/watch?v=abc123"


@pytest.fixture
def home(db):
    return Site.objects.get(is_default_site=True).root_page.specific


@pytest.fixture
def context(home):
    return render_context(home)


@pytest.fixture
def form_page(home):
    return home.add_child(instance=Page(title="Join us", slug="join"))


@pytest.fixture(autouse=True)
def no_embed_provider(monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("an embed provider was called")

    monkeypatch.setattr("wagtail.embeds.finders.get_finders", fail)


def render(block_class, raw, context):
    block = block_class()
    return render_block(block, block.to_python(raw), context)


def text(html):
    return {"type": "text", "value": html}


@pytest.fixture
def image(db, settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)
    return get_image_model().objects.create(title="Rally", file=get_test_image_file())


@pytest.fixture
def actionkit_context(context):
    integration = SimpleNamespace(
        get_integration_config=lambda slug: {"hostname": "campaigns.example.org"}
    )
    return {**context, "settings": {"wtrx": {"IntegrationSettings": integration}}}


def test_image_keeps_caption_and_local_alt_override(context, image):
    raw = {"image": image.pk, "alt_text": "Marchers [together]", "caption": "Nairobi, 2026"}
    output = render(wtrx.ImageBlock, raw, context)
    assert output.startswith("![Marchers \\[together\\]](")
    assert output.endswith("\n\nNairobi, 2026")
    assert render(wtrx.ImageBlock, {"image": image.pk}, context).startswith("![Rally](")


def test_page_cards_links_only_the_index_without_reading_children(context, form_page, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("page cards must not query children or render a template")

    monkeypatch.setattr(Page, "get_children", fail)
    monkeypatch.setattr(wtrx.PageCardsBlock, "render", fail)
    output = render(
        wtrx.PageCardsBlock,
        {
            "content": "<h2>Latest updates</h2><p>Our campaigns.</p>",
            "index_page": form_page.pk,
            "link_text": "All updates",
        },
        context,
    )
    assert output == "## Latest updates\n\nOur campaigns.\n\n[All updates](/join/)"
    assert render(wtrx.PageCardsBlock, {"index_page": form_page.pk, "link_text": ""}, context) == (
        "[Read more](/join/)"
    )


def test_body_hero_has_h2_copy_and_caption(context):
    assert (
        render(
            wtrx.HeroBlock,
            {
                "headline": "People power",
                "content": "<p>Act together.</p>",
                "image_caption": "Photo: Ada",
            },
            context,
        )
        == "## People power\n\nAct together.\n\nPhoto: Ada"
    )


def test_fundraiseup_keeps_content_image_and_caption_only(context, image):
    output = render(
        wtrx.DonateFundraiseUpBlock,
        {
            "content": "<h2>Support the campaign</h2>",
            "image": image.pk,
            "image_caption": "Photo: Ada",
            "designation_id": "DO-NOT-EXPORT",
            "advanced_settings": {"element_id_default": "DO-NOT-EXPORT"},
        },
        context,
    )
    assert output.startswith("## Support the campaign\n\n![Rally](")
    assert output.endswith("\n\nPhoto: Ada")
    assert "DO-NOT-EXPORT" not in output


@pytest.mark.parametrize("shortname", ["climate-action", "join_kenya"])
def test_actionkit_links_each_campaign_offline(actionkit_context, shortname, monkeypatch):
    def fail(*args, **kwargs):
        raise AssertionError("must not render or fetch the ActionKit form")

    monkeypatch.setattr(wtrx.SignupActionKitBlock, "render", fail)
    raw = {
        "eyebrow": "Campaign",
        "content": "<h2>Act now</h2>",
        "short_form_id": shortname,
        "image_caption": "Photo: Ada",
        "success_message": [text("<p>SUCCESS MUST NOT LEAK</p>")],
    }
    assert render(wtrx.SignupActionKitBlock, raw, actionkit_context) == (
        "Campaign\n\n## Act now\n\nPhoto: Ada\n\n"
        f"[Take action](https://campaigns.example.org/act/{shortname}/)"
    )
    assert render(wtrx.HeroSignupActionKitBlock, raw, actionkit_context) == (
        f"[Take action](https://campaigns.example.org/act/{shortname}/)"
    )


@pytest.mark.parametrize(
    "hostname", ["act.example.org", "https://act.example.org/", "http://act.example.org"]
)
def test_actionkit_uses_the_page_sites_settings(context, hostname):
    context["settings"] = {
        "wtrx": {
            "IntegrationSettings": SimpleNamespace(
                get_integration_config=lambda slug: {"hostname": hostname}
            )
        }
    }
    expected = hostname.rstrip("/")
    if "://" not in expected:
        expected = "https://" + expected
    assert render(wtrx.HeroSignupActionKitBlock, {"short_form_id": "join"}, context) == (
        f"[Take action]({expected}/act/join/)"
    )


@pytest.mark.parametrize("config", [None, {}, {"hostname": ""}])
def test_actionkit_unconfigured_keeps_prose_without_fake_link(context, config):
    context["settings"] = {
        "wtrx": {"IntegrationSettings": SimpleNamespace(get_integration_config=lambda slug: config)}
    }
    assert (
        render(
            wtrx.SignupActionKitBlock,
            {"short_form_id": "join", "content": "<p>Join us.</p>"},
            context,
        )
        == "Join us."
    )


def test_actionkit_rejects_credentials_in_hostname(context):
    context["settings"] = {
        "wtrx": {
            "IntegrationSettings": SimpleNamespace(
                get_integration_config=lambda slug: {
                    "hostname": "https://user:secret@act.example.org"
                }
            )
        }
    }
    with pytest.raises(ImproperlyConfigured, match="ActionKit requires"):
        render(wtrx.SignupActionKitBlock, {"short_form_id": "join"}, context)


@pytest.fixture
def hero_page(home):
    from wtrx.models import ContentPage

    page = home.add_child(
        instance=ContentPage(
            title="Document title",
            slug="hero-page",
            hero_headline="Hero headline",
            hero_pre_header="Our campaign",
            hero_copy="<p>Hero copy.</p>",
            hero_image_caption="Hero caption",
            hero_cta=[("button", {"text": "Join", "link_url": "https://example.org/join"})],
            body=[
                ("text", "<p>Body content.</p>"),
                ("hero", {"headline": "Body hero", "image_caption": "Body caption"}),
            ],
        )
    )
    page.save_revision().publish()
    return page


def body_of(page):
    return render_page(page).split("---\n", 2)[2].strip()


def test_page_hero_is_assembled_once_before_body(hero_page):
    assert body_of(hero_page) == (
        "# Hero headline\n\nOur campaign\n\nHero copy.\n\n[Join](https://example.org/join)"
        "\n\nHero caption\n\nBody content.\n\n## Body hero\n\nBody caption"
    )


def test_hide_hero_uses_published_state_and_omits_entire_page_hero(hero_page):
    hero_page.hide_hero = True
    hero_page.save_revision()
    assert "Hero copy." in body_of(hero_page)  # A newer draft cannot hide the live hero.
    hero_page.save_revision().publish()
    assert body_of(hero_page) == (
        "# Document title\n\nBody content.\n\n## Body hero\n\nBody caption"
    )


def test_explicit_hero_fields_fail_instead_of_duplicating_or_leaking(hero_page, settings):
    settings.WAGTAIL_MARKDOWN_AGENTS = {"PAGE_FIELDS": {"wtrx.ContentPage": ["hero_copy", "body"]}}
    with pytest.raises(ImproperlyConfigured, match="omit them from PAGE_FIELDS"):
        render_page(hero_page)


def test_homepage_actionkit_hero_uses_offline_context(home, actionkit_context, monkeypatch):
    from wtrx.models import HomePage

    page = home.add_child(
        instance=HomePage(
            title="Home",
            slug="campaign-home",
            hero_cta=[("signup", {"short_form_id": "campaign-one"})],
            body=[("text", "<p>Campaign body.</p>")],
        )
    )
    page.save_revision().publish()
    original = render_context

    def with_settings(page, site=None):
        return {**original(page, site), "settings": actionkit_context["settings"]}

    monkeypatch.setattr("wagtail_markdown_agents.rendering.page.render_context", with_settings)
    assert body_of(page) == (
        "# Home\n\n[Take action](https://campaigns.example.org/act/campaign-one/)\n\nCampaign body."
    )


@pytest.mark.parametrize(
    "model_name,expected",
    [
        ("HomePage", ["body"]),
        ("ContentPage", ["body"]),
        ("IndexPage", ["intro", "body"]),
        ("Post", ["body"]),
        ("Blogs", []),
    ],
)
def test_page_type_field_defaults(model_name, expected):
    from wtrx import models

    from wagtail_markdown_agents.rendering.page import selected_fields

    assert [field.name for field in selected_fields(getattr(models, model_name))] == expected


def test_index_hero_precedes_intro_body_and_generated_navigation(home):
    from wtrx.models import IndexPage

    page = home.add_child(
        instance=IndexPage(
            title="Index",
            slug="campaign-index",
            hero_copy="<p>Hero copy.</p>",
            intro="<p>Introduction.</p>",
            body=[("text", "<p>Body.</p>")],
        )
    )
    page.save_revision().publish()
    output = render_page(page, navigation="- [Child](/child/)").split("---\n", 2)[2].strip()
    assert output == "# Index\n\nHero copy.\n\nIntroduction.\n\nBody.\n\n- [Child](/child/)"


# Leaves


def test_video_embed_links_the_url_with_its_caption(context):
    raw = {"embed_url": YOUTUBE, "caption": "Our story"}

    assert render(wtrx.VideoBlock, raw, context) == f"[Our story]({YOUTUBE})"


def test_video_embed_uses_a_stored_title_or_an_autolink(context):
    assert render(wtrx.VideoBlock, {"embed_url": YOUTUBE}, context) == f"<{YOUTUBE}>"

    Embed.objects.create(url=YOUTUBE, hash=embeds.get_embed_hash(YOUTUBE), title="Stored title")
    assert render(wtrx.VideoBlock, {"embed_url": YOUTUBE}, context) == f"[Stored title]({YOUTUBE})"


def test_video_file_links_the_absolute_media_url(context, settings):
    settings.WAGTAILADMIN_BASE_URL = "https://350.org"
    media = SimpleNamespace(title="Launch", url="/media/launch.mp4")
    raw = {"media_file": media, "caption": "Filmed in Nairobi"}

    assert render(wtrx.VideoBlock, raw, context) == (
        "[Launch](https://350.org/media/launch.mp4)\n\nFilmed in Nairobi"
    )


def test_button_links_a_page_or_url_and_omits_style(context, form_page):
    assert render(wtrx.ButtonBlock, {"text": "Join", "link_page": form_page.pk}, context) == (
        "[Join](/join/)"
    )
    assert render(wtrx.ButtonBlock, {"text": "Act", "link_url": "https://x.org"}, context) == (
        "[Act](https://x.org)"
    )


def test_anchor_only_button_is_left_out(context):
    assert render(wtrx.ButtonBlock, {"text": "Sign up", "anchor": "petition"}, context) == ""


def test_button_group_is_a_list_of_links_without_anchor_buttons(context):
    raw = {
        "buttons": [
            {"text": "Donate", "link_url": "https://x.org/donate"},
            {"text": "Jump", "anchor": "petition"},
            {"text": "Volunteer", "link_url": "https://x.org/volunteer"},
        ]
    }

    assert render(wtrx.ButtonGroupBlock, raw, context) == (
        "- [Donate](https://x.org/donate)\n- [Volunteer](https://x.org/volunteer)"
    )


def test_quote_is_a_blockquote_then_its_link(context):
    raw = {
        "content": "<p>We are unstoppable.</p><p>Another world is possible.</p>",
        "link_text": "Read the story",
        "link_url": "https://x.org/story",
        "alignment": "left",
    }

    assert render(wtrx.QuoteBlock, raw, context) == (
        "> We are unstoppable.\n>\n> Another world is possible.\n\n"
        "[Read the story](https://x.org/story)"
    )


def test_card_puts_the_tag_under_its_heading_and_omits_the_icon(context):
    raw = {
        "tag": "Global",
        "content": "<h3>Fossil free</h3><p>Divest now.</p>",
        "link_url": "https://x.org/divest",
    }

    assert render(wtrx.CardBlock, raw, context) == (
        "### Fossil free\n\nGlobal\n\nDivest now.\n\n[Learn more](https://x.org/divest)"
    )


def test_card_without_a_link_has_no_call_to_action(context):
    raw = {"content": "<h3>Fossil free</h3>", "link_text": "Learn more"}

    assert render(wtrx.CardBlock, raw, context) == "### Fossil free"


def test_person_card_appears_once_with_contact_links(context):
    raw = {
        "name": "Ada Okafor",
        "role": "Campaigner",
        "bio": "Ada leads the Africa team.",
        "email": "ada@350.org",
        "phone": "+254 700 000000",
        "website": "https://ada.example",
    }

    assert render(wtrx.PersonCardBlock, raw, context) == (
        "### Ada Okafor\n\nCampaigner\n\nAda leads the Africa team.\n\n"
        "[ada@350.org](mailto:ada@350.org) · [+254 700 000000](tel:+254 700 000000) · "
        "[Website](https://ada.example)"
    )


def test_signup_wagtail_forms_links_the_form_page_without_the_success_message(context, form_page):
    raw = {
        "content": "<p>Get updates.</p>",
        "form_page": form_page.pk,
        "success_message": "Thanks for signing up!",
    }

    output = render(wtrx.SignupWagtailFormsBlock, raw, context)

    assert output == "Get updates.\n\n[Sign Up](/join/)"


def test_signup_action_network_links_the_action_without_the_success_stream(context):
    raw = {
        "content": "<p>Add your name.</p>",
        "action_url": "https://actionnetwork.org/forms/x",
        "success_message": [text("<p>You're in!</p>")],
    }

    assert render(wtrx.SignupActionNetworkBlock, raw, context) == (
        "Add your name.\n\n[Sign Up](https://actionnetwork.org/forms/x)"
    )


# Containers reach their children's renderers


def test_card_grid_renders_each_card(context):
    raw = {
        "heading": "Campaigns",
        "cards": [
            {"content": "<h3>One</h3>", "link_url": "https://x.org/1"},
            {"content": "<h3>Two</h3>", "link_url": "https://x.org/2", "link_text": "Go"},
        ],
    }

    assert render(wtrx.CardGridBlock, raw, context) == (
        "## Campaigns\n\n### One\n\n[Learn more](https://x.org/1)\n\n### Two\n\n[Go](https://x.org/2)"
    )


def test_person_card_grid_renders_each_person_once(context):
    raw = {"heading": "Team", "people": [{"name": "Ada"}, {"name": "Bo"}]}

    assert render(wtrx.PersonCardGridBlock, raw, context) == "## Team\n\n### Ada\n\n### Bo"


def test_empty_grids_leave_no_heading(context):
    assert render(wtrx.CardGridBlock, {"heading": "Campaigns", "cards": []}, context) == ""
    assert render(wtrx.PersonCardGridBlock, {"heading": "Team", "people": []}, context) == ""


def test_card_carousel_has_its_intro_link_and_cards(context):
    raw = {
        "content": "<p>Latest wins.</p>",
        "link_text": "All wins",
        "link_url": "https://x.org/wins",
        "cards": [{"content": "<h3>Win</h3>", "link_url": "https://x.org/win"}],
    }

    assert render(wtrx.CardCarouselBlock, raw, context) == (
        "Latest wins.\n\n[All wins](https://x.org/wins)\n\n### Win\n\n[Learn more](https://x.org/win)"
    )


def test_accordion_titles_become_headings_over_their_content(context):
    raw = {
        "heading": "FAQ",
        "items": [
            {"title": "Why?", "content": [text("<p>Because.</p>")]},
            {"title": "Watch", "content": [{"type": "video", "value": {"embed_url": YOUTUBE}}]},
        ],
    }

    assert render(wtrx.AccordionBlock, raw, context) == (
        f"## FAQ\n\n### Why?\n\nBecause.\n\n### Watch\n\n<{YOUTUBE}>"
    )


def test_section_renders_its_content_in_place(context):
    raw = {
        "content": [
            text("<p>Intro.</p>"),
            {"type": "button", "value": {"text": "Jump", "anchor": "petition"}},
            {"type": "card", "value": {"content": "<h3>Card</h3>"}},
        ],
        "background": "white",
        "anchor_id": "section-1",
    }

    assert render(wtrx.SectionBlock, raw, context) == "Intro.\n\n### Card"


def test_timeline_years_are_headings_without_the_year_navigation(context):
    raw = {
        "years": [
            {"year": "2019", "content": [text("<p>Strikes.</p>")]},
            {
                "year": "2020",
                "content": [{"type": "video", "value": {"embed_url": YOUTUBE, "caption": "Clip"}}],
            },
        ]
    }

    assert render(wtrx.TimelineBlock, raw, context) == (
        f"## 2019\n\nStrikes.\n\n## 2020\n\n[Clip]({YOUTUBE})"
    )


def test_nested_containers_reach_leaf_renderers(context):
    accordion = {
        "heading": "",
        "items": [
            {
                "title": "Signup",
                "content": [text("<p>Join.</p>")],
            }
        ],
    }
    raw = {
        "content": [
            {"type": "accordion", "value": accordion},
            {
                "type": "signup_action_network",
                "value": {
                    "action_url": "https://an.org/f",
                    "success_message": [text("<p>Yay</p>")],
                },
            },
        ]
    }

    assert render(wtrx.SectionBlock, raw, context) == (
        "### Signup\n\nJoin.\n\n[Sign Up](https://an.org/f)"
    )
