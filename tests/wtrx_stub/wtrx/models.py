"""Synthetic page fields used by the 350.org page assembly tests.

Only the public content fields read by the add-on are represented. No site
integrations, credentials or private data are needed.
"""

from django.db import models
from wagtail.fields import RichTextField, StreamField
from wagtail.models import Page

from .blocks import HeroCTABlock, SectionContentBlock


class HeroMixin(models.Model):
    hero_headline = models.CharField(max_length=255, blank=True)
    hero_pre_header = models.CharField(max_length=255, blank=True)
    hero_copy = RichTextField(blank=True)
    hero_cta = StreamField(HeroCTABlock(), blank=True)
    hero_image_caption = models.CharField(max_length=255, blank=True)

    class Meta:
        abstract = True


class HomePage(Page, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    page_ptr = models.OneToOneField(
        Page, on_delete=models.CASCADE, parent_link=True, primary_key=True, related_name="+"
    )
    body = StreamField(SectionContentBlock(), blank=True)


class ContentPage(Page, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    page_ptr = models.OneToOneField(
        Page, on_delete=models.CASCADE, parent_link=True, primary_key=True, related_name="+"
    )
    hide_hero = models.BooleanField(default=False)
    body = StreamField(SectionContentBlock(), blank=True)


class IndexPage(Page, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    intro = RichTextField(blank=True)
    body = StreamField(SectionContentBlock(), blank=True)


class Blogs(Page, HeroMixin):  # noqa: DJ008 — inherits Page.__str__
    pass


class Post(Page):
    hero_headline = models.CharField(max_length=255, blank=True)
    body = StreamField(SectionContentBlock(), blank=True)
