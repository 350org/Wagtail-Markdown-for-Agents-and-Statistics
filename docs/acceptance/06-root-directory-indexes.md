# 06 — Root and directory indexes

Project-owner authorised through the request to implement #20 after #72/#14.
The package defaults below are covered with synthetic fixtures; 350.org's final
presentation sign-off remains separate from this implementation.

- Rebuilding a page-owned index renders its published body and frontmatter again,
  appending one generated navigation list. Never replace it with navigation alone.
  The physical root index carries the package's `OKF_VERSION` as `okf_version`.
- List only current, readable page-owned exports from the same enabled site, using
  their actual named public URLs. Use published titles and search descriptions,
  deterministic title order, and a count of listed entries. Never list drafts,
  restricted/excluded/vetoed, missing or ungenerated targets.
- Follow the logical export directories. A child page-owned index represents its
  subtree. If an intermediate page has no export, surface its available descendants
  directly. Supply standalone indexes for directories without page-owned indexes;
  these use generic navigation metadata, never an excluded parent's title/body.
- An empty corpus still has a root index with zero entries and an explicit empty
  message. Empty non-root synthetic directories disappear after source changes.
- Expose a navigation-content hook with site, path, published owning page (if any),
  entries and count. It can customise or suppress the listing without receiving or
  replacing the parent's body/frontmatter. Errors abort the affected publication.
- Synthetic 350-style output preserves hero, intro and body in that order, then one
  complete title-ordered export listing, including more than 12 children. This is
  export navigation, independent of the HTML listing's pagination. A project that
  supplies an authored listing can explicitly suppress the generated one.
- Coalesce repeated dirty sites in an explicit batch and finalise once after page
  writes. Capture existing parent indexes before withdrawal so leaf/index transitions
  can be rebuilt. Revocation still withdraws private metadata immediately, including
  on a failed batch; obsolete builds cannot restore it.
- Use the existing reserved-name allocation, including collisions with escaped names
  and identity suffixes. Never overwrite another page's owned path. A real page can
  safely take over a standalone navigation index at its newly assigned index path.
- Verify filesystem and remote storage, direct HTTP retrieval, obsolete builds,
  published-revision isolation, repeated rebuilds and SQLite/PostgreSQL.
