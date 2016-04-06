# Writing Ruleset Tests

To generate a new ruleset test, create a `LESS` file  in the `rulesets` folder, named `testname.less`. The first line of the `LESS` file should be a line comment (starts with `\\`) that contains the short description of the test. This will be displayed along with the name of the test , when running from unittest.  Install the companion HTML in the html folder, as `testname_raw.html` and `testname_cooked.html` You can generate the cooked content
with `cnx-easybake` as so:

```
$ lessc rulesets/testname.less rulesets/testname.css
$ cnx-easybake rulesets/testname.css html/testname_raw.html html/testname_cooked.html
```
The test framework now runs in DEBUG level logging and checks for log output as well. This
can be added to the LESS file as so:

```
$ ./update-log-less.sh [testname]
```
 If the testname is omitted, all LESS files will be updated.
