#!/bin/bash
rulename=${1:-*}
sed -i '\;^// LOG: ;d' rulesets/${rulename}.less
for r in rulesets/${rulename}.less
    do
        file=$(basename $r)
        name=${file%%.less}
        echo $name
        lessc rulesets/${name}.less rulesets/${name}.css
        cnx-easybake -d rulesets/${name}.css html/${name}_raw.html html/${name}_cooked.html.tmp 2>&1 | sed 's;^;// LOG: ;' >> rulesets/${name}.less
        if ! cmp html/${name}_cooked.html{,.tmp};  then
            diff -u html/${name}_cooked.html{.tmp,}
            mv html/${name}_cooked.html{.tmp,}
        else
            rm html/${name}_cooked.html.tmp
        fi
        touch rulesets/${name}.css
    done  
