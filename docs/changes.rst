==========
Change Log
==========

1.2.1
-----

- Add tests for stripping away unquoted escape characters in the `match` pseudo-selector


1.2.0
-----

- Update to depend on cnx-cssselect2 instead of a github repo named cssselect2


1.1.0
-----

- Update parser behavior in response to cssselect2 changes (#86)
- Pin the version of pyICU for mac (#84)
- Add support for namespace prefixes in `container:` (#81)
  - Properly handle namespace prefixes in container:
  - Add tests for namespace prefixes in content:
- Add locale aware behavior for sorting and grouping (#79)
