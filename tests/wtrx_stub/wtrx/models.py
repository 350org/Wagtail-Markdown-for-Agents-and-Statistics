"""Synthetic page fields used by the 350.org profile tests.

Only the public content fields the profile reads are represented, with the
field types of the site's ``wtrx/models.py`` on ``main`` as of 16 October 2026.
No site integrations, credentials or private data are needed. wagtailmedia
isn't a test dependency, so there is no ``hero_video`` field; the hero hook
reads it with ``getattr``.
"""

from django.db import models
from modelcluster.fields import ParentalKey, ParentalManyToManyField
from modelcluster.models import ClusterableModel
from wagtail import blocks
from wagtail.contrib.settings.models import BaseSiteSetting
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Locale, Orderable, Page

from .blocks import HeroCTABlock, SectionContentBlock


class BasePage(Page):
    hide_from_search = models.BooleanField(default=False)
    canonical_url = models.URLField(blank=True)

    class Meta:
        abstract = True


class HeroMixin(models.Model):
    hero_headline = RichTextField(blank=True)
    hero_pre_header = models.CharField(max_length=255, blank=True)
    hero_copy = RichTextField(blank=True)
    hero_cta = StreamField(HeroCTABlock(), blank=True)
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    hero_image_caption = models.CharField(max_length=255, blank=True)

    hero_variant = "banner"

    class Meta:
        abstract = True


class HomePage(BasePage, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    # The sandbox has models with the same names; keep Page's accessors to theirs.
    page_ptr = models.OneToOneField(
        Page, on_delete=models.CASCADE, parent_link=True, primary_key=True, related_name="+"
    )
    body = StreamField(SectionContentBlock(), blank=True)

    hero_variant = "full"


class ContentPage(BasePage, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    # The sandbox has models with the same names; keep Page's accessors to theirs.
    page_ptr = models.OneToOneField(
        Page, on_delete=models.CASCADE, parent_link=True, primary_key=True, related_name="+"
    )
    hide_hero = models.BooleanField(default=False)
    body = StreamField(SectionContentBlock(), blank=True)


class IndexPage(BasePage, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    intro = RichTextField(blank=True)
    body = StreamField(SectionContentBlock(), blank=True)


class Blogs(BasePage, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    pass


class BlogCategory(ClusterableModel):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def label_for(self, locale):
        for label in self.labels.all():
            if label.locale_id == locale.pk:
                return label.name
        return self.name


class BlogCategoryLabel(Orderable):
    category = ParentalKey(BlogCategory, on_delete=models.CASCADE, related_name="labels")
    locale = models.ForeignKey(Locale, on_delete=models.PROTECT, related_name="+")
    name = models.CharField(max_length=100)


class Post(BasePage):  # noqa: DJ008 — inherits Page.__str__
    hero_headline = RichTextField(blank=True)
    hero_image = models.ForeignKey(
        "wagtailimages.Image", null=True, blank=True, on_delete=models.SET_NULL, related_name="+"
    )
    published_at = models.DateTimeField(null=True, blank=True)
    author_name = models.CharField(max_length=255, blank=True)
    author_title = models.CharField(max_length=255, blank=True)
    categories = ParentalManyToManyField(BlogCategory, blank=True, related_name="posts")
    body = StreamField(SectionContentBlock(), blank=True)

    @property
    def author_display(self):
        if self.author_name:
            if self.author_title:
                return f"{self.author_name}, {self.author_title}"
            return self.author_name
        return None


class IntegrationSettings(BaseSiteSetting):
    """Only fields needed to test settings saves and offline configuration reads."""

    integrations = StreamField(
        [
            (
                "actionkit",
                blocks.StructBlock(
                    [
                        ("enabled", blocks.BooleanBlock(required=False, default=True)),
                        ("hostname", blocks.CharBlock(required=False)),
                    ]
                ),
            ),
            (
                "actblue",
                blocks.StructBlock(
                    [
                        ("enabled", blocks.BooleanBlock(required=False, default=True)),
                        ("base_url", blocks.URLBlock(required=False)),
                        ("suggested_amounts", blocks.CharBlock(required=False)),
                    ]
                ),
            ),
        ],
        blank=True,
    )
    custom_head_html = models.TextField(blank=True)
    custom_body_html = models.TextField(blank=True)

    def get_integration_config(self, slug):
        for block in self.integrations:
            if block.block_type == slug and block.value.get("enabled", True):
                return block.value
        return None
