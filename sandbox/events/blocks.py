from wagtail import blocks


class EventBlock(blocks.StructBlock):
    title = blocks.CharBlock()
    date = blocks.DateBlock()
    location = blocks.CharBlock(required=False)
    summary = blocks.RichTextBlock(required=False)
    style = blocks.ChoiceBlock(choices=[("light", "Light"), ("dark", "Dark")], default="light")

    class Meta:
        template = "events/event_block.html"


class EventListBlock(blocks.StructBlock):
    heading = blocks.CharBlock()
    events = blocks.ListBlock(EventBlock())
