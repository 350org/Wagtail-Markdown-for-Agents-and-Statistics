from django.db import models


class AgentAccess(models.Model):
    """Daily response-selection counts; page history survives CMS deletion."""

    # Deliberately not a foreign key: deleting a page must retain its history.
    page_id = models.PositiveIntegerField()
    agent = models.CharField(max_length=100, blank=True)
    access_method = models.CharField(max_length=20)
    access_date = models.DateField(db_index=True)
    count = models.PositiveBigIntegerField(default=1)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["page_id", "agent", "access_method", "access_date"],
                name="agentmd_access_daily_unique",
            ),
        ]

    def __str__(self):
        return f"{self.agent or 'unknown'}: page {self.page_id} ({self.access_date})"


class PageAgentSettings(models.Model):
    """Per-page Markdown-export settings, kept out of host page models.

    A side-model (rather than a required mixin) so the package is drop-in on
    unmodified page models. An absent row means the page is included —
    opt-out semantics, matching the WordPress plugin's exclusion meta.
    """

    page = models.OneToOneField(
        "wagtailcore.Page",
        on_delete=models.CASCADE,
        related_name="agent_markdown_settings",
    )
    excluded = models.BooleanField(
        default=False,
        help_text="Exclude this page from Markdown export and agent serving.",
    )
    extra_frontmatter = models.JSONField(
        default=dict,
        blank=True,
        help_text="Additional frontmatter keys merged into this page's export.",
    )

    class Meta:
        verbose_name = "page agent Markdown settings"
        verbose_name_plural = "page agent Markdown settings"

    def __str__(self) -> str:
        return f"Agent Markdown settings for page {self.page_id}"


class ExportScope(models.Model):
    """Database publication mutex and monotonic generation for one site.

    IDs deliberately survive deletion of the corresponding Wagtail site/page:
    cleanup must not lose its inventory through a foreign-key cascade.
    """

    site_id = models.PositiveIntegerField(unique=True)
    version = models.PositiveBigIntegerField(default=0)
    content_version = models.PositiveBigIntegerField(default=0)
    # Private comparison hashes survive withdrawal of the public manifest.
    manifest_state = models.JSONField(default=dict, blank=True)

    def __str__(self):
        return f"Export scope for site {self.site_id}"


class ExportFile(models.Model):
    """An immutable storage object, retained until managed cleanup succeeds."""

    scope = models.ForeignKey(ExportScope, on_delete=models.PROTECT)
    page_id = models.PositiveIntegerField(null=True)
    logical_path = models.CharField(max_length=1024)
    storage_alias = models.CharField(max_length=255, blank=True)
    storage_fingerprint = models.CharField(max_length=64)
    requested_key = models.CharField(max_length=1024)
    storage_key = models.CharField(max_length=1024)
    cleanup_pending = models.BooleanField(default=False)
    notify_deleted = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.storage_key


class ExportArtifact(models.Model):
    """Stable logical path pointing to the last successfully published file."""

    scope = models.ForeignKey(ExportScope, on_delete=models.PROTECT)
    page_id = models.PositiveIntegerField(null=True)
    logical_path = models.CharField(max_length=1024, unique=True)
    file = models.OneToOneField(ExportFile, on_delete=models.PROTECT, related_name="artifact")
    source_state = models.CharField(max_length=64)
    dependency_state = models.CharField(max_length=64, blank=True, default="")
    published_at = models.DateTimeField(auto_now=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["scope", "page_id"], name="agentmd_scope_page_unique"),
        ]

    def __str__(self):
        return self.logical_path
