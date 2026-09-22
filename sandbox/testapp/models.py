"""Test page models with a StreamField covering every built-in renderer case:
rich text, heading, image, embed, table, and Struct/List/StreamBlock nesting.
"""

from django.db import models
from modelcluster.contrib.taggit import ClusterTaggableManager
from modelcluster.fields import ParentalKey
from taggit.models import TaggedItemBase
from wagtail import blocks
from wagtail.admin.panels import FieldPanel
from wagtail.contrib.forms.models import AbstractForm
from wagtail.contrib.table_block.blocks import TableBlock
from wagtail.embeds.blocks import EmbedBlock
from wagtail.fields import RichTextField, StreamField
from wagtail.images.blocks import ImageChooserBlock
from wagtail.models import Page

from wagtail_markdown_agents.panels import AgentMarkdownPanelMixin


class CalloutBlock(blocks.StructBlock):
    """Nested StructBlock: title + rich body."""

    title = blocks.CharBlock(required=False)
    body = blocks.RichTextBlock()

    class Meta:
        icon = "warning"


class SectionBlock(blocks.StructBlock):
    """StructBlock containing a nested StreamBlock — the recursion case."""

    heading = blocks.CharBlock()
    content = blocks.StreamBlock(
        [
            ("paragraph", blocks.RichTextBlock()),
            ("callout", CalloutBlock()),
        ],
        required=False,
    )


class BodyBlock(blocks.StreamBlock):
    heading = blocks.CharBlock()
    paragraph = blocks.RichTextBlock()
    image = ImageChooserBlock(required=False)
    embed = EmbedBlock(required=False)
    table = TableBlock(required=False)
    callout = CalloutBlock()
    bullet_points = blocks.ListBlock(blocks.CharBlock())
    section = SectionBlock()
    raw_html = blocks.RawHTMLBlock(required=False)


class HomePage(Page):
    subpage_types = ["testapp.ArticlePage", "testapp.HomePage"]


class ArticlePageTag(TaggedItemBase):
    content_object = ParentalKey(
        "testapp.ArticlePage", related_name="tagged_items", on_delete=models.CASCADE
    )


class ArticlePageTopic(TaggedItemBase):
    """A second tag field, so flat tags are proven to merge across fields (#13)."""

    content_object = ParentalKey(
        "testapp.ArticlePage", related_name="topic_items", on_delete=models.CASCADE
    )


class ArticlePage(Page):
    body = StreamField(BodyBlock(), blank=True)
    tags = ClusterTaggableManager(through=ArticlePageTag, blank=True)
    topics = ClusterTaggableManager(through=ArticlePageTopic, blank=True, related_name="+")

    content_panels = Page.content_panels + [
        FieldPanel("body"),
        FieldPanel("tags"),
        FieldPanel("topics"),
    ]


class MarkdownArticlePage(AgentMarkdownPanelMixin, ArticlePage):
    """Separate opt-in page type, leaving the generic ArticlePage baseline intact."""


class ContentPage(Page):
    """Synthetic page-level fields for orchestration tests; no wtrx dependency."""

    hero_headline = models.CharField(max_length=255, blank=True)
    hero_copy = RichTextField(blank=True)
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    hero_link_text = models.CharField(max_length=255, blank=True)
    hero_link_page = models.ForeignKey(
        "wagtailcore.Page", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    intro = RichTextField(blank=True)
    body = StreamField(BodyBlock(), blank=True)


class FormPage(AbstractForm):
    """Even a form with renderable fields must not be reported as a complete export."""

    intro = RichTextField(blank=True)
    body = StreamField(BodyBlock(), blank=True)
