# Development and test project

This Wagtail project is the package's test target and local demonstration site.
Keep it with the source checkout: pytest uses `sandbox.settings`, and integration
tests depend on its models, migrations, renderers and templates.

| Path | Purpose |
| --- | --- |
| `settings.py`, `urls.py`, `manage.py` | Local SQLite project with the package, middleware and public routes installed. |
| `testapp/` | Synthetic page models, rendering fixtures and simulator setup commands. |
| `events/` | Example custom block and renderer registration. |
| `postgres_settings.py` | PostgreSQL compatibility tests using `AGENTMD_TEST_*` environment variables. |
| `mysql_settings.py` | Isolated statistics write benchmark; not a supported full application deployment. |
| `simulator_settings.py` | Separate local simulator corpus, database and export storage. |

The settings deliberately use a fixed test secret and `DEBUG=True`; do not deploy
this project. Database credentials in the test settings are disposable local
defaults, overridden through environment variables. Install the package into your
own project using [INSTALL.md](../INSTALL.md).

Local databases, uploaded media, collected static files, generated exports and
simulator run data are ignored by Git. Committed templates and model fixtures are
synthetic test assets. The sandbox is included in the source distribution for
reproducibility and excluded from the installed runtime wheel.

For setup and sample content, use the
[development guide](../docs/contributing/development.md); for automated checks,
see the [test guide](../tests/README.md).
