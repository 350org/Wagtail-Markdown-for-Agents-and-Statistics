# 07 — llms.txt discovery

Project-owner authorised after the example and scope discussion for #21.

- Publish a Markdown-formatted `llms.txt` through the existing managed text route.
  Use one site-name H1 (hostname fallback), an optional configured plain-text
  introduction as a blockquote, then an Explore section of links with descriptions.
  No YAML, timestamps, generated marketing copy or complete page bodies.
- Link the current readable root index, when available, and the root directory's
  available page exports in deterministic title order. A child page-owned index
  represents its descendants; otherwise surface the available descendants directly.
  Do not invent semantic categories or truncate a directory's entries arbitrarily.
- Use actual absolute public URLs, including custom route prefixes and relocated
  exports. Only the current enabled site's eligible, readable, managed artefacts
  qualify. Published titles/descriptions must not reveal newer drafts. Missing,
  ungenerated, stale, excluded, restricted, inherited-private and vetoed targets
  contribute neither links nor metadata.
- An empty corpus still produces a site heading and an explicit empty message,
  unless a readable root index provides a navigation target. Never borrow metadata
  from an unexported root page.
- Escape site names, introduction, titles, descriptions and Markdown URL delimiters.
  An invalid introduction setting fails before publication, retaining previous bytes.
- Repeated builds from unchanged inputs produce identical bytes. Site-name or
  introduction changes invalidate previous discovery output even in an empty corpus.
  Changing only the introduction does not invalidate ordinary leaf exports.
- Capture publication state before collecting links. Reject work superseded by
  publication/revocation, including changes during storage upload. Newly private
  metadata becomes unavailable immediately through managed reads, and a subsequent
  build omits it. Failed uploads preserve the previous complete current document.
- Finalise llms.txt once per dirty site, after its indexes. Failure leaves that site
  dirty for retry; completed batches do no work on a second finalisation. Automatic
  lifecycle receivers and management commands remain their separate issues.
- Verify filesystem and remote storage, GET/HEAD and direct traversal of generated
  links, the supported compatibility matrix, PostgreSQL and a reviewed golden file.
