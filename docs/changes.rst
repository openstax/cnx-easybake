==========
Change Log
==========

1.2.7
-----

- Add missing environment variable to Jenkinsfile (#110)

1.2.6
-----

- Fix errors when expressions evaluated to the empty string (#109)

1.2.5
-----

- Fix py3 cnx-easybake script output invalid html (#106)

1.2.4
-----

- Fix unicode encode error in TargetVal.__str__ (#105)

1.2.3
-----

- Recognize error from deletion on '::outside' (#91)

1.2.2
-----

- Re-release of 1.2.1

1.2.1
-----

- Add tests for stripping away unquoted escape characters in the `match` pseudo-selector (#100)
- Make cnx-easybake python3 compatible (#101)
- Add Jenkinsfile (#102)


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
