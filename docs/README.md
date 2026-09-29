# Package documentation

Start with [installation](../INSTALL.md) for requirements, configuration, upgrades
and removal. These guides explain how to use the package in a Wagtail project.

| Task | Guide |
| --- | --- |
| Choose how clients request Markdown | [Content negotiation](negotiation.md) |
| Configure a CDN or page cache | [Caching](cdn-caching.md) |
| Advertise Markdown from HTML | [Discovery headers and template tag](discovery-headers.md) |
| Serve generated files | [Public routes](public-export-routes.md), [storage](storage-writer.md) |
| Generate navigation and discovery files | [Indexes](indexes.md), [llms.txt](llms-txt.md), [manifest](manifest.md) |
| Render pages and custom blocks | [Page rendering](page-rendering.md), [custom blocks](custom-blocks.md), [internal links](internal-links.md) |
| Run commands and diagnose configuration | [Management commands](management-commands.md), [system checks](system-checks.md) |
| Understand automatic generation and revocation | [Publication lifecycle](publish-lifecycle.md) |
| Add an editor exclusion checkbox | [Editor panel](editor-exclusion-panel.md) |
| Read statistics and agent classifications | [Access statistics](agent-access-stats.md), [agent registry](agent-registry.md) |
| Test a deployment with controlled traffic | [Agent simulator](agent-simulator.md) |

[Contributor documentation](contributing/README.md) covers development,
architecture, benchmarks, provenance reviews and releases.
