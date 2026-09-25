import django.db.models.deletion
import wagtail.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("wagtailcore", "0069_log_entry_jsonfield"),
    ]

    operations = [
        migrations.CreateModel(
            name="Blogs",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                ("hero_headline", models.CharField(blank=True, max_length=255)),
                ("hero_pre_header", models.CharField(blank=True, max_length=255)),
                ("hero_copy", wagtail.fields.RichTextField(blank=True)),
                (
                    "hero_cta",
                    wagtail.fields.StreamField(
                        [("button", 6), ("signup", 16)],
                        blank=True,
                        block_lookup={
                            0: ("wagtail.blocks.CharBlock", (), {}),
                            1: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            2: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            3: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            4: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            5: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 0),
                                        ("link_page", 1),
                                        ("link_url", 2),
                                        ("anchor", 3),
                                        ("style", 4),
                                        ("size", 5),
                                    ]
                                ],
                                {},
                            ),
                            7: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            8: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            9: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            10: (
                                "wagtail.images.blocks.ImageChooserBlock",
                                (),
                                {"required": False},
                            ),
                            11: ("wtrx.blocks.IdentifierBlock", (), {}),
                            12: ("wtrx.blocks.TextBlock", (), {}),
                            13: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            14: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 13), ("alt_text", 7), ("caption", 7)]],
                                {},
                            ),
                            15: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 12), ("image", 14), ("button", 6)]],
                                {"required": False},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 7),
                                        ("background", 8),
                                        ("layout", 9),
                                        ("image", 10),
                                        ("image_caption", 7),
                                        ("short_form_id", 11),
                                        ("anchor_id", 3),
                                        ("success_message", 15),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
                ("hero_image_caption", models.CharField(blank=True, max_length=255)),
            ],
            options={
                "abstract": False,
            },
            bases=("wagtailcore.page", models.Model),
        ),
        migrations.CreateModel(
            name="ContentPage",
            fields=[
                ("hero_headline", models.CharField(blank=True, max_length=255)),
                ("hero_pre_header", models.CharField(blank=True, max_length=255)),
                ("hero_copy", wagtail.fields.RichTextField(blank=True)),
                (
                    "hero_cta",
                    wagtail.fields.StreamField(
                        [("button", 6), ("signup", 16)],
                        blank=True,
                        block_lookup={
                            0: ("wagtail.blocks.CharBlock", (), {}),
                            1: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            2: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            3: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            4: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            5: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 0),
                                        ("link_page", 1),
                                        ("link_url", 2),
                                        ("anchor", 3),
                                        ("style", 4),
                                        ("size", 5),
                                    ]
                                ],
                                {},
                            ),
                            7: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            8: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            9: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            10: (
                                "wagtail.images.blocks.ImageChooserBlock",
                                (),
                                {"required": False},
                            ),
                            11: ("wtrx.blocks.IdentifierBlock", (), {}),
                            12: ("wtrx.blocks.TextBlock", (), {}),
                            13: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            14: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 13), ("alt_text", 7), ("caption", 7)]],
                                {},
                            ),
                            15: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 12), ("image", 14), ("button", 6)]],
                                {"required": False},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 7),
                                        ("background", 8),
                                        ("layout", 9),
                                        ("image", 10),
                                        ("image_caption", 7),
                                        ("short_form_id", 11),
                                        ("anchor_id", 3),
                                        ("success_message", 15),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
                ("hero_image_caption", models.CharField(blank=True, max_length=255)),
                (
                    "page_ptr",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                ("hide_hero", models.BooleanField(default=False)),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [
                            ("text", 0),
                            ("lead_text", 1),
                            ("heading", 3),
                            ("image", 6),
                            ("hero", 10),
                            ("page_cards", 13),
                            ("donate_fundraiseup", 17),
                            ("video", 20),
                            ("button", 24),
                            ("button_group", 27),
                            ("quote", 30),
                            ("card", 33),
                            ("person_card", 36),
                            ("card_grid", 38),
                            ("accordion", 42),
                            ("signup_wagtail_forms", 43),
                            ("signup_action_network", 46),
                            ("signup_actionkit", 50),
                        ],
                        blank=True,
                        block_lookup={
                            0: ("wtrx.blocks.TextBlock", (), {}),
                            1: ("wtrx.blocks.LeadTextBlock", (), {}),
                            2: ("wagtail.blocks.CharBlock", (), {}),
                            3: ("wagtail.blocks.StructBlock", [[("heading", 2)]], {}),
                            4: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            5: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 4), ("alt_text", 5), ("caption", 5)]],
                                {},
                            ),
                            7: ("wagtail.blocks.RichTextBlock", (), {"required": False}),
                            8: ("wagtail.images.blocks.ImageChooserBlock", (), {"required": False}),
                            9: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("navy", "Navy")]}),
                            10: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("headline", 2),
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("banner_color", 9),
                                    ]
                                ],
                                {},
                            ),
                            11: ("wagtail.blocks.PageChooserBlock", (), {}),
                            12: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Read more", "required": False},
                            ),
                            13: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("index_page", 11),
                                        ("category", 5),
                                        ("link_text", 12),
                                    ]
                                ],
                                {},
                            ),
                            14: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            15: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("image-left", "Left")]},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("element_id_us", 14),
                                        ("element_id_nl", 14),
                                        ("element_id_ca", 14),
                                        ("element_id_gb", 14),
                                        ("eu_country_codes", 14),
                                        ("element_id_eu", 14),
                                        ("element_id_default", 14),
                                    ]
                                ],
                                {"required": False},
                            ),
                            17: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("designation_id", 14),
                                        ("alignment", 15),
                                        ("advanced_settings", 16),
                                    ]
                                ],
                                {},
                            ),
                            18: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            19: ("wtrx.blocks.VideoChooserBlock", (), {"required": False}),
                            20: (
                                "wagtail.blocks.StructBlock",
                                [[("embed_url", 18), ("media_file", 19), ("caption", 5)]],
                                {},
                            ),
                            21: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            22: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            23: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            24: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 2),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("anchor", 14),
                                        ("style", 22),
                                        ("size", 23),
                                    ]
                                ],
                                {},
                            ),
                            25: ("wagtail.blocks.ListBlock", (24,), {}),
                            26: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("horizontal", "Horizontal")]},
                            ),
                            27: (
                                "wagtail.blocks.StructBlock",
                                [[("buttons", 25), ("layout", 26)]],
                                {},
                            ),
                            28: ("wagtail.blocks.RichTextBlock", (), {}),
                            29: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("left", "Left")]}),
                            30: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 28),
                                        ("image", 8),
                                        ("media_file", 19),
                                        ("link_text", 5),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("alignment", 29),
                                    ]
                                ],
                                {},
                            ),
                            31: (
                                "wagtail.documents.blocks.DocumentChooserBlock",
                                (),
                                {"required": False},
                            ),
                            32: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Learn more", "required": False},
                            ),
                            33: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("tag", 5),
                                        ("icon", 8),
                                        ("content", 28),
                                        ("image", 8),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("link_document", 31),
                                        ("link_text", 32),
                                    ]
                                ],
                                {},
                            ),
                            34: ("wagtail.blocks.TextBlock", (), {"required": False}),
                            35: ("wagtail.blocks.EmailBlock", (), {"required": False}),
                            36: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("name", 2),
                                        ("role", 5),
                                        ("image", 8),
                                        ("bio", 34),
                                        ("email", 35),
                                        ("phone", 5),
                                        ("website", 18),
                                    ]
                                ],
                                {},
                            ),
                            37: ("wagtail.blocks.ListBlock", (33,), {}),
                            38: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("cards", 37)]],
                                {},
                            ),
                            39: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("video", 20)]],
                                {},
                            ),
                            40: (
                                "wagtail.blocks.StructBlock",
                                [[("title", 2), ("content", 39)]],
                                {},
                            ),
                            41: ("wagtail.blocks.ListBlock", (40,), {}),
                            42: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("items", 41)]],
                                {},
                            ),
                            43: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("button_text", 5),
                                        ("form_page", 11),
                                        ("success_message", 5),
                                    ]
                                ],
                                {},
                            ),
                            44: ("wagtail.blocks.URLBlock", (), {}),
                            45: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("button", 24)]],
                                {"required": False},
                            ),
                            46: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("action_url", 44),
                                        ("success_message", 45),
                                        ("anchor_id", 14),
                                    ]
                                ],
                                {},
                            ),
                            47: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            48: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            49: ("wtrx.blocks.IdentifierBlock", (), {}),
                            50: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 5),
                                        ("background", 47),
                                        ("layout", 48),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("short_form_id", 49),
                                        ("anchor_id", 14),
                                        ("success_message", 45),
                                        ("content", 7),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("wagtailcore.page", models.Model),
        ),
        migrations.CreateModel(
            name="HomePage",
            fields=[
                ("hero_headline", models.CharField(blank=True, max_length=255)),
                ("hero_pre_header", models.CharField(blank=True, max_length=255)),
                ("hero_copy", wagtail.fields.RichTextField(blank=True)),
                (
                    "hero_cta",
                    wagtail.fields.StreamField(
                        [("button", 6), ("signup", 16)],
                        blank=True,
                        block_lookup={
                            0: ("wagtail.blocks.CharBlock", (), {}),
                            1: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            2: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            3: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            4: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            5: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 0),
                                        ("link_page", 1),
                                        ("link_url", 2),
                                        ("anchor", 3),
                                        ("style", 4),
                                        ("size", 5),
                                    ]
                                ],
                                {},
                            ),
                            7: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            8: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            9: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            10: (
                                "wagtail.images.blocks.ImageChooserBlock",
                                (),
                                {"required": False},
                            ),
                            11: ("wtrx.blocks.IdentifierBlock", (), {}),
                            12: ("wtrx.blocks.TextBlock", (), {}),
                            13: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            14: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 13), ("alt_text", 7), ("caption", 7)]],
                                {},
                            ),
                            15: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 12), ("image", 14), ("button", 6)]],
                                {"required": False},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 7),
                                        ("background", 8),
                                        ("layout", 9),
                                        ("image", 10),
                                        ("image_caption", 7),
                                        ("short_form_id", 11),
                                        ("anchor_id", 3),
                                        ("success_message", 15),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
                ("hero_image_caption", models.CharField(blank=True, max_length=255)),
                (
                    "page_ptr",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        related_name="+",
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [
                            ("text", 0),
                            ("lead_text", 1),
                            ("heading", 3),
                            ("image", 6),
                            ("hero", 10),
                            ("page_cards", 13),
                            ("donate_fundraiseup", 17),
                            ("video", 20),
                            ("button", 24),
                            ("button_group", 27),
                            ("quote", 30),
                            ("card", 33),
                            ("person_card", 36),
                            ("card_grid", 38),
                            ("accordion", 42),
                            ("signup_wagtail_forms", 43),
                            ("signup_action_network", 46),
                            ("signup_actionkit", 50),
                        ],
                        blank=True,
                        block_lookup={
                            0: ("wtrx.blocks.TextBlock", (), {}),
                            1: ("wtrx.blocks.LeadTextBlock", (), {}),
                            2: ("wagtail.blocks.CharBlock", (), {}),
                            3: ("wagtail.blocks.StructBlock", [[("heading", 2)]], {}),
                            4: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            5: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 4), ("alt_text", 5), ("caption", 5)]],
                                {},
                            ),
                            7: ("wagtail.blocks.RichTextBlock", (), {"required": False}),
                            8: ("wagtail.images.blocks.ImageChooserBlock", (), {"required": False}),
                            9: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("navy", "Navy")]}),
                            10: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("headline", 2),
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("banner_color", 9),
                                    ]
                                ],
                                {},
                            ),
                            11: ("wagtail.blocks.PageChooserBlock", (), {}),
                            12: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Read more", "required": False},
                            ),
                            13: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("index_page", 11),
                                        ("category", 5),
                                        ("link_text", 12),
                                    ]
                                ],
                                {},
                            ),
                            14: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            15: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("image-left", "Left")]},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("element_id_us", 14),
                                        ("element_id_nl", 14),
                                        ("element_id_ca", 14),
                                        ("element_id_gb", 14),
                                        ("eu_country_codes", 14),
                                        ("element_id_eu", 14),
                                        ("element_id_default", 14),
                                    ]
                                ],
                                {"required": False},
                            ),
                            17: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("designation_id", 14),
                                        ("alignment", 15),
                                        ("advanced_settings", 16),
                                    ]
                                ],
                                {},
                            ),
                            18: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            19: ("wtrx.blocks.VideoChooserBlock", (), {"required": False}),
                            20: (
                                "wagtail.blocks.StructBlock",
                                [[("embed_url", 18), ("media_file", 19), ("caption", 5)]],
                                {},
                            ),
                            21: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            22: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            23: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            24: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 2),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("anchor", 14),
                                        ("style", 22),
                                        ("size", 23),
                                    ]
                                ],
                                {},
                            ),
                            25: ("wagtail.blocks.ListBlock", (24,), {}),
                            26: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("horizontal", "Horizontal")]},
                            ),
                            27: (
                                "wagtail.blocks.StructBlock",
                                [[("buttons", 25), ("layout", 26)]],
                                {},
                            ),
                            28: ("wagtail.blocks.RichTextBlock", (), {}),
                            29: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("left", "Left")]}),
                            30: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 28),
                                        ("image", 8),
                                        ("media_file", 19),
                                        ("link_text", 5),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("alignment", 29),
                                    ]
                                ],
                                {},
                            ),
                            31: (
                                "wagtail.documents.blocks.DocumentChooserBlock",
                                (),
                                {"required": False},
                            ),
                            32: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Learn more", "required": False},
                            ),
                            33: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("tag", 5),
                                        ("icon", 8),
                                        ("content", 28),
                                        ("image", 8),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("link_document", 31),
                                        ("link_text", 32),
                                    ]
                                ],
                                {},
                            ),
                            34: ("wagtail.blocks.TextBlock", (), {"required": False}),
                            35: ("wagtail.blocks.EmailBlock", (), {"required": False}),
                            36: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("name", 2),
                                        ("role", 5),
                                        ("image", 8),
                                        ("bio", 34),
                                        ("email", 35),
                                        ("phone", 5),
                                        ("website", 18),
                                    ]
                                ],
                                {},
                            ),
                            37: ("wagtail.blocks.ListBlock", (33,), {}),
                            38: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("cards", 37)]],
                                {},
                            ),
                            39: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("video", 20)]],
                                {},
                            ),
                            40: (
                                "wagtail.blocks.StructBlock",
                                [[("title", 2), ("content", 39)]],
                                {},
                            ),
                            41: ("wagtail.blocks.ListBlock", (40,), {}),
                            42: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("items", 41)]],
                                {},
                            ),
                            43: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("button_text", 5),
                                        ("form_page", 11),
                                        ("success_message", 5),
                                    ]
                                ],
                                {},
                            ),
                            44: ("wagtail.blocks.URLBlock", (), {}),
                            45: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("button", 24)]],
                                {"required": False},
                            ),
                            46: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("action_url", 44),
                                        ("success_message", 45),
                                        ("anchor_id", 14),
                                    ]
                                ],
                                {},
                            ),
                            47: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            48: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            49: ("wtrx.blocks.IdentifierBlock", (), {}),
                            50: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 5),
                                        ("background", 47),
                                        ("layout", 48),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("short_form_id", 49),
                                        ("anchor_id", 14),
                                        ("success_message", 45),
                                        ("content", 7),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("wagtailcore.page", models.Model),
        ),
        migrations.CreateModel(
            name="IndexPage",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                ("hero_headline", models.CharField(blank=True, max_length=255)),
                ("hero_pre_header", models.CharField(blank=True, max_length=255)),
                ("hero_copy", wagtail.fields.RichTextField(blank=True)),
                (
                    "hero_cta",
                    wagtail.fields.StreamField(
                        [("button", 6), ("signup", 16)],
                        blank=True,
                        block_lookup={
                            0: ("wagtail.blocks.CharBlock", (), {}),
                            1: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            2: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            3: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            4: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            5: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 0),
                                        ("link_page", 1),
                                        ("link_url", 2),
                                        ("anchor", 3),
                                        ("style", 4),
                                        ("size", 5),
                                    ]
                                ],
                                {},
                            ),
                            7: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            8: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            9: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            10: (
                                "wagtail.images.blocks.ImageChooserBlock",
                                (),
                                {"required": False},
                            ),
                            11: ("wtrx.blocks.IdentifierBlock", (), {}),
                            12: ("wtrx.blocks.TextBlock", (), {}),
                            13: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            14: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 13), ("alt_text", 7), ("caption", 7)]],
                                {},
                            ),
                            15: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 12), ("image", 14), ("button", 6)]],
                                {"required": False},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 7),
                                        ("background", 8),
                                        ("layout", 9),
                                        ("image", 10),
                                        ("image_caption", 7),
                                        ("short_form_id", 11),
                                        ("anchor_id", 3),
                                        ("success_message", 15),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
                ("hero_image_caption", models.CharField(blank=True, max_length=255)),
                ("intro", wagtail.fields.RichTextField(blank=True)),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [
                            ("text", 0),
                            ("lead_text", 1),
                            ("heading", 3),
                            ("image", 6),
                            ("hero", 10),
                            ("page_cards", 13),
                            ("donate_fundraiseup", 17),
                            ("video", 20),
                            ("button", 24),
                            ("button_group", 27),
                            ("quote", 30),
                            ("card", 33),
                            ("person_card", 36),
                            ("card_grid", 38),
                            ("accordion", 42),
                            ("signup_wagtail_forms", 43),
                            ("signup_action_network", 46),
                            ("signup_actionkit", 50),
                        ],
                        blank=True,
                        block_lookup={
                            0: ("wtrx.blocks.TextBlock", (), {}),
                            1: ("wtrx.blocks.LeadTextBlock", (), {}),
                            2: ("wagtail.blocks.CharBlock", (), {}),
                            3: ("wagtail.blocks.StructBlock", [[("heading", 2)]], {}),
                            4: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            5: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 4), ("alt_text", 5), ("caption", 5)]],
                                {},
                            ),
                            7: ("wagtail.blocks.RichTextBlock", (), {"required": False}),
                            8: ("wagtail.images.blocks.ImageChooserBlock", (), {"required": False}),
                            9: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("navy", "Navy")]}),
                            10: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("headline", 2),
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("banner_color", 9),
                                    ]
                                ],
                                {},
                            ),
                            11: ("wagtail.blocks.PageChooserBlock", (), {}),
                            12: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Read more", "required": False},
                            ),
                            13: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("index_page", 11),
                                        ("category", 5),
                                        ("link_text", 12),
                                    ]
                                ],
                                {},
                            ),
                            14: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            15: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("image-left", "Left")]},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("element_id_us", 14),
                                        ("element_id_nl", 14),
                                        ("element_id_ca", 14),
                                        ("element_id_gb", 14),
                                        ("eu_country_codes", 14),
                                        ("element_id_eu", 14),
                                        ("element_id_default", 14),
                                    ]
                                ],
                                {"required": False},
                            ),
                            17: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("designation_id", 14),
                                        ("alignment", 15),
                                        ("advanced_settings", 16),
                                    ]
                                ],
                                {},
                            ),
                            18: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            19: ("wtrx.blocks.VideoChooserBlock", (), {"required": False}),
                            20: (
                                "wagtail.blocks.StructBlock",
                                [[("embed_url", 18), ("media_file", 19), ("caption", 5)]],
                                {},
                            ),
                            21: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            22: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            23: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            24: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 2),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("anchor", 14),
                                        ("style", 22),
                                        ("size", 23),
                                    ]
                                ],
                                {},
                            ),
                            25: ("wagtail.blocks.ListBlock", (24,), {}),
                            26: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("horizontal", "Horizontal")]},
                            ),
                            27: (
                                "wagtail.blocks.StructBlock",
                                [[("buttons", 25), ("layout", 26)]],
                                {},
                            ),
                            28: ("wagtail.blocks.RichTextBlock", (), {}),
                            29: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("left", "Left")]}),
                            30: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 28),
                                        ("image", 8),
                                        ("media_file", 19),
                                        ("link_text", 5),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("alignment", 29),
                                    ]
                                ],
                                {},
                            ),
                            31: (
                                "wagtail.documents.blocks.DocumentChooserBlock",
                                (),
                                {"required": False},
                            ),
                            32: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Learn more", "required": False},
                            ),
                            33: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("tag", 5),
                                        ("icon", 8),
                                        ("content", 28),
                                        ("image", 8),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("link_document", 31),
                                        ("link_text", 32),
                                    ]
                                ],
                                {},
                            ),
                            34: ("wagtail.blocks.TextBlock", (), {"required": False}),
                            35: ("wagtail.blocks.EmailBlock", (), {"required": False}),
                            36: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("name", 2),
                                        ("role", 5),
                                        ("image", 8),
                                        ("bio", 34),
                                        ("email", 35),
                                        ("phone", 5),
                                        ("website", 18),
                                    ]
                                ],
                                {},
                            ),
                            37: ("wagtail.blocks.ListBlock", (33,), {}),
                            38: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("cards", 37)]],
                                {},
                            ),
                            39: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("video", 20)]],
                                {},
                            ),
                            40: (
                                "wagtail.blocks.StructBlock",
                                [[("title", 2), ("content", 39)]],
                                {},
                            ),
                            41: ("wagtail.blocks.ListBlock", (40,), {}),
                            42: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("items", 41)]],
                                {},
                            ),
                            43: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("button_text", 5),
                                        ("form_page", 11),
                                        ("success_message", 5),
                                    ]
                                ],
                                {},
                            ),
                            44: ("wagtail.blocks.URLBlock", (), {}),
                            45: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("button", 24)]],
                                {"required": False},
                            ),
                            46: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("action_url", 44),
                                        ("success_message", 45),
                                        ("anchor_id", 14),
                                    ]
                                ],
                                {},
                            ),
                            47: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            48: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            49: ("wtrx.blocks.IdentifierBlock", (), {}),
                            50: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 5),
                                        ("background", 47),
                                        ("layout", 48),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("short_form_id", 49),
                                        ("anchor_id", 14),
                                        ("success_message", 45),
                                        ("content", 7),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("wagtailcore.page", models.Model),
        ),
        migrations.CreateModel(
            name="Post",
            fields=[
                (
                    "page_ptr",
                    models.OneToOneField(
                        auto_created=True,
                        on_delete=django.db.models.deletion.CASCADE,
                        parent_link=True,
                        primary_key=True,
                        serialize=False,
                        to="wagtailcore.page",
                    ),
                ),
                ("hero_headline", models.CharField(blank=True, max_length=255)),
                (
                    "body",
                    wagtail.fields.StreamField(
                        [
                            ("text", 0),
                            ("lead_text", 1),
                            ("heading", 3),
                            ("image", 6),
                            ("hero", 10),
                            ("page_cards", 13),
                            ("donate_fundraiseup", 17),
                            ("video", 20),
                            ("button", 24),
                            ("button_group", 27),
                            ("quote", 30),
                            ("card", 33),
                            ("person_card", 36),
                            ("card_grid", 38),
                            ("accordion", 42),
                            ("signup_wagtail_forms", 43),
                            ("signup_action_network", 46),
                            ("signup_actionkit", 50),
                        ],
                        blank=True,
                        block_lookup={
                            0: ("wtrx.blocks.TextBlock", (), {}),
                            1: ("wtrx.blocks.LeadTextBlock", (), {}),
                            2: ("wagtail.blocks.CharBlock", (), {}),
                            3: ("wagtail.blocks.StructBlock", [[("heading", 2)]], {}),
                            4: ("wagtail.images.blocks.ImageChooserBlock", (), {}),
                            5: ("wagtail.blocks.CharBlock", (), {"required": False}),
                            6: (
                                "wagtail.blocks.StructBlock",
                                [[("image", 4), ("alt_text", 5), ("caption", 5)]],
                                {},
                            ),
                            7: ("wagtail.blocks.RichTextBlock", (), {"required": False}),
                            8: ("wagtail.images.blocks.ImageChooserBlock", (), {"required": False}),
                            9: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("navy", "Navy")]}),
                            10: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("headline", 2),
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("banner_color", 9),
                                    ]
                                ],
                                {},
                            ),
                            11: ("wagtail.blocks.PageChooserBlock", (), {}),
                            12: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Read more", "required": False},
                            ),
                            13: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("index_page", 11),
                                        ("category", 5),
                                        ("link_text", 12),
                                    ]
                                ],
                                {},
                            ),
                            14: ("wtrx.blocks.IdentifierBlock", (), {"required": False}),
                            15: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("image-left", "Left")]},
                            ),
                            16: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("element_id_us", 14),
                                        ("element_id_nl", 14),
                                        ("element_id_ca", 14),
                                        ("element_id_gb", 14),
                                        ("eu_country_codes", 14),
                                        ("element_id_eu", 14),
                                        ("element_id_default", 14),
                                    ]
                                ],
                                {"required": False},
                            ),
                            17: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("designation_id", 14),
                                        ("alignment", 15),
                                        ("advanced_settings", 16),
                                    ]
                                ],
                                {},
                            ),
                            18: ("wagtail.blocks.URLBlock", (), {"required": False}),
                            19: ("wtrx.blocks.VideoChooserBlock", (), {"required": False}),
                            20: (
                                "wagtail.blocks.StructBlock",
                                [[("embed_url", 18), ("media_file", 19), ("caption", 5)]],
                                {},
                            ),
                            21: ("wagtail.blocks.PageChooserBlock", (), {"required": False}),
                            22: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("primary", "Primary")]},
                            ),
                            23: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("regular", "Regular")]},
                            ),
                            24: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("text", 2),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("anchor", 14),
                                        ("style", 22),
                                        ("size", 23),
                                    ]
                                ],
                                {},
                            ),
                            25: ("wagtail.blocks.ListBlock", (24,), {}),
                            26: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("horizontal", "Horizontal")]},
                            ),
                            27: (
                                "wagtail.blocks.StructBlock",
                                [[("buttons", 25), ("layout", 26)]],
                                {},
                            ),
                            28: ("wagtail.blocks.RichTextBlock", (), {}),
                            29: ("wagtail.blocks.ChoiceBlock", [], {"choices": [("left", "Left")]}),
                            30: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 28),
                                        ("image", 8),
                                        ("media_file", 19),
                                        ("link_text", 5),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("alignment", 29),
                                    ]
                                ],
                                {},
                            ),
                            31: (
                                "wagtail.documents.blocks.DocumentChooserBlock",
                                (),
                                {"required": False},
                            ),
                            32: (
                                "wagtail.blocks.CharBlock",
                                (),
                                {"default": "Learn more", "required": False},
                            ),
                            33: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("tag", 5),
                                        ("icon", 8),
                                        ("content", 28),
                                        ("image", 8),
                                        ("link_page", 21),
                                        ("link_url", 18),
                                        ("link_document", 31),
                                        ("link_text", 32),
                                    ]
                                ],
                                {},
                            ),
                            34: ("wagtail.blocks.TextBlock", (), {"required": False}),
                            35: ("wagtail.blocks.EmailBlock", (), {"required": False}),
                            36: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("name", 2),
                                        ("role", 5),
                                        ("image", 8),
                                        ("bio", 34),
                                        ("email", 35),
                                        ("phone", 5),
                                        ("website", 18),
                                    ]
                                ],
                                {},
                            ),
                            37: ("wagtail.blocks.ListBlock", (33,), {}),
                            38: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("cards", 37)]],
                                {},
                            ),
                            39: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("video", 20)]],
                                {},
                            ),
                            40: (
                                "wagtail.blocks.StructBlock",
                                [[("title", 2), ("content", 39)]],
                                {},
                            ),
                            41: ("wagtail.blocks.ListBlock", (40,), {}),
                            42: (
                                "wagtail.blocks.StructBlock",
                                [[("heading", 5), ("items", 41)]],
                                {},
                            ),
                            43: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("button_text", 5),
                                        ("form_page", 11),
                                        ("success_message", 5),
                                    ]
                                ],
                                {},
                            ),
                            44: ("wagtail.blocks.URLBlock", (), {}),
                            45: (
                                "wagtail.blocks.StreamBlock",
                                [[("text", 0), ("image", 6), ("button", 24)]],
                                {"required": False},
                            ),
                            46: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("content", 7),
                                        ("action_url", 44),
                                        ("success_message", 45),
                                        ("anchor_id", 14),
                                    ]
                                ],
                                {},
                            ),
                            47: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("dark-grey", "Dark grey")]},
                            ),
                            48: (
                                "wagtail.blocks.ChoiceBlock",
                                [],
                                {"choices": [("columns", "Side by side")]},
                            ),
                            49: ("wtrx.blocks.IdentifierBlock", (), {}),
                            50: (
                                "wagtail.blocks.StructBlock",
                                [
                                    [
                                        ("eyebrow", 5),
                                        ("background", 47),
                                        ("layout", 48),
                                        ("image", 8),
                                        ("image_caption", 5),
                                        ("short_form_id", 49),
                                        ("anchor_id", 14),
                                        ("success_message", 45),
                                        ("content", 7),
                                    ]
                                ],
                                {},
                            ),
                        },
                    ),
                ),
            ],
            options={
                "abstract": False,
            },
            bases=("wagtailcore.page",),
        ),
    ]
