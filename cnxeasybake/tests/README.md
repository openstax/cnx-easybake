# Writing Ruleset Tests

To generate a new ruleset test, create a `CSS` file  in the `rulesets` folder, named `testname.css`. The first line of the `CSS` file should be a comment that contains the short description of the test.  Install the companion HTML in the html folder, as `testname_raw.html` and `testname_cooked.html` You can generate the cooked content as so:

```
$ ./scripts/update-test-results testname  # From the git root
```
 If the testname is omitted, all CSS files will be updated.
