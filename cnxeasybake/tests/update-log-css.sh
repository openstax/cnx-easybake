#!/bin/bash
set -e

rulename=${*:-*}
for r in rulesets/${rulename}.css
    do
        file=$(basename $r)
        name=${file%%.css}
        echo $name
        cnx-easybake -d rulesets/${name}.css html/${name}_raw.html html/${name}_cooked.html.tmp 2> html/${name}.log
        if ! cmp html/${name}_cooked.html{,.tmp};  then
            diff -u html/${name}_cooked.html{,.tmp}
            mv html/${name}_cooked.html{.tmp,}
        else
            rm html/${name}_cooked.html.tmp
        fi
        touch rulesets/${name}.css
    done
