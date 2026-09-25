"""The 350.org blocks the contrib.wtrx renderers cover, as a stand-in (#14).

Mirrors the field names, field types and nesting of ``wtrx/blocks/__init__.py``
in ``350org/wagtail-wtr-350`` branch ``improvements`` at 1997766. Help text,
validation, previews and templates are left out: the renderers read only the
fields. wagtailmedia isn't a test dependency, so ``VideoChooserBlock`` is a
stand-in whose value is the media object itself.
"""

from django import forms
from wagtail import blocks
from wagtail.documents.blocks import DocumentChooserBlock
from wagtail.images.blocks import ImageChooserBlock


class VideoChooserBlock(blocks.FieldBlock):
    """Stand-in for ``wagtailmedia.blocks.VideoChooserBlock``."""

    def __init__(self, **kwargs):
        self.field = forms.Field(required=False)
        super().__init__(**kwargs)

    def to_python(self, value):
        return value


class IdentifierBlock(blocks.CharBlock):
    pass


STYLE = [("primary", "Primary")]


class TextBlock(blocks.RichTextBlock):
    pass


class LeadTextBlock(blocks.RichTextBlock):
    pass


class HeadingBlock(blocks.StructBlock):
    heading = blocks.CharBlock()


class ImageBlock(blocks.StructBlock):
    image = ImageChooserBlock()
    alt_text = blocks.CharBlock(required=False)
    caption = blocks.CharBlock(required=False)


class PageCardsBlock(blocks.StructBlock):
    content = blocks.RichTextBlock(required=False)
    index_page = blocks.PageChooserBlock()
    category = blocks.CharBlock(required=False)  # Unused snippet chooser stand-in.
    link_text = blocks.CharBlock(required=False, default="Read more")


class HeroBlock(blocks.StructBlock):
    headline = blocks.CharBlock()
    content = blocks.RichTextBlock(required=False)
    image = ImageChooserBlock(required=False)
    image_caption = blocks.CharBlock(required=False)
    banner_color = blocks.ChoiceBlock(choices=[("navy", "Navy")], default="navy")


class DonateFundraiseUpBlock(blocks.StructBlock):
    content = blocks.RichTextBlock(required=False)
    image = ImageChooserBlock(required=False)
    image_caption = blocks.CharBlock(required=False)
    designation_id = IdentifierBlock(required=False)
    alignment = blocks.ChoiceBlock(choices=[("image-left", "Left")], default="image-left")
    advanced_settings = blocks.StructBlock(
        [
            (name, IdentifierBlock(required=False))
            for name in (
                "element_id_us",
                "element_id_nl",
                "element_id_ca",
                "element_id_gb",
                "eu_country_codes",
                "element_id_eu",
                "element_id_default",
            )
        ],
        required=False,
    )


class VideoBlock(blocks.StructBlock):
    embed_url = blocks.URLBlock(required=False)
    media_file = VideoChooserBlock(required=False)
    caption = blocks.CharBlock(required=False)


class ButtonBlock(blocks.StructBlock):
    text = blocks.CharBlock()
    link_page = blocks.PageChooserBlock(required=False)
    link_url = blocks.URLBlock(required=False)
    anchor = IdentifierBlock(required=False)
    style = blocks.ChoiceBlock(choices=STYLE, default="primary")
    size = blocks.ChoiceBlock(choices=[("regular", "Regular")], default="regular")


class ButtonGroupBlock(blocks.StructBlock):
    buttons = blocks.ListBlock(ButtonBlock())
    layout = blocks.ChoiceBlock(choices=[("horizontal", "Horizontal")], default="horizontal")


class CardBlock(blocks.StructBlock):
    tag = blocks.CharBlock(required=False)
    icon = ImageChooserBlock(required=False)
    content = blocks.RichTextBlock()
    image = ImageChooserBlock(required=False)
    link_page = blocks.PageChooserBlock(required=False)
    link_url = blocks.URLBlock(required=False)
    link_document = DocumentChooserBlock(required=False)
    link_text = blocks.CharBlock(required=False, default="Learn more")


class CarouselCardBlock(CardBlock):
    image = ImageChooserBlock()


class PersonCardBlock(blocks.StructBlock):
    name = blocks.CharBlock()
    role = blocks.CharBlock(required=False)
    image = ImageChooserBlock(required=False)
    bio = blocks.TextBlock(required=False)
    email = blocks.EmailBlock(required=False)
    phone = blocks.CharBlock(required=False)
    website = blocks.URLBlock(required=False)


class AccordionItemContentBlock(blocks.StreamBlock):
    text = TextBlock()
    image = ImageBlock()
    video = VideoBlock()


class AccordionItemBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    content = AccordionItemContentBlock()


class CardGridBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False)
    cards = blocks.ListBlock(CardBlock())


class PersonCardGridBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False)
    people = blocks.ListBlock(PersonCardBlock())


class CardCarouselBlock(blocks.StructBlock):
    content = blocks.RichTextBlock(required=False)
    link_text = blocks.CharBlock(required=False)
    link_page = blocks.PageChooserBlock(required=False)
    link_url = blocks.URLBlock(required=False)
    cards = blocks.ListBlock(CarouselCardBlock())


class AccordionBlock(blocks.StructBlock):
    heading = blocks.CharBlock(required=False)
    items = blocks.ListBlock(AccordionItemBlock())


class QuoteBlock(blocks.StructBlock):
    content = blocks.RichTextBlock()
    image = ImageChooserBlock(required=False)
    media_file = VideoChooserBlock(required=False)
    link_text = blocks.CharBlock(required=False)
    link_page = blocks.PageChooserBlock(required=False)
    link_url = blocks.URLBlock(required=False)
    alignment = blocks.ChoiceBlock(choices=[("left", "Left")], default="left")


class SignupWagtailFormsBlock(blocks.StructBlock):
    content = blocks.RichTextBlock(required=False)
    button_text = blocks.CharBlock(required=False)
    form_page = blocks.PageChooserBlock()
    success_message = blocks.CharBlock(required=False)


class SuccessMessageBlock(blocks.StreamBlock):
    text = TextBlock()
    image = ImageBlock()
    button = ButtonBlock()


class SignupActionNetworkBlock(blocks.StructBlock):
    content = blocks.RichTextBlock(required=False)
    action_url = blocks.URLBlock()
    success_message = SuccessMessageBlock(required=False)
    anchor_id = IdentifierBlock(required=False)


class HeroSignupActionKitBlock(blocks.StructBlock):
    eyebrow = blocks.CharBlock(required=False)
    background = blocks.ChoiceBlock(choices=[("dark-grey", "Dark grey")], default="dark-grey")
    layout = blocks.ChoiceBlock(choices=[("columns", "Side by side")], default="columns")
    image = ImageChooserBlock(required=False)
    image_caption = blocks.CharBlock(required=False)
    short_form_id = IdentifierBlock()
    anchor_id = IdentifierBlock(required=False)
    success_message = SuccessMessageBlock(required=False)


class SignupActionKitBlock(HeroSignupActionKitBlock):
    # The real classes are siblings sharing a mixin; fields are otherwise identical.
    content = blocks.RichTextBlock(required=False)


class HeroCTABlock(blocks.StreamBlock):
    button = ButtonBlock()
    signup = HeroSignupActionKitBlock()


class SectionContentBlock(blocks.StreamBlock):
    """A subset of the site's 29 children: the ones these tests nest."""

    text = TextBlock()
    lead_text = LeadTextBlock()
    heading = HeadingBlock()
    image = ImageBlock()
    hero = HeroBlock()
    page_cards = PageCardsBlock()
    donate_fundraiseup = DonateFundraiseUpBlock()
    video = VideoBlock()
    button = ButtonBlock()
    button_group = ButtonGroupBlock()
    quote = QuoteBlock()
    card = CardBlock()
    person_card = PersonCardBlock()
    card_grid = CardGridBlock()
    accordion = AccordionBlock()
    signup_wagtail_forms = SignupWagtailFormsBlock()
    signup_action_network = SignupActionNetworkBlock()
    signup_actionkit = SignupActionKitBlock()


class SectionBlock(blocks.StructBlock):
    content = SectionContentBlock()
    background = blocks.ChoiceBlock(choices=[("white", "White")], default="white")
    padding = blocks.ChoiceBlock(choices=[("regular", "Regular")], default="regular")
    width = blocks.ChoiceBlock(choices=[("regular", "Regular")], default="regular")
    anchor_id = IdentifierBlock(required=False)


class TimelineYearContentBlock(SectionContentBlock):
    pass


class TimelineYearBlock(blocks.StructBlock):
    year = IdentifierBlock()
    content = TimelineYearContentBlock()


class TimelineBlock(blocks.StructBlock):
    years = blocks.ListBlock(TimelineYearBlock())
