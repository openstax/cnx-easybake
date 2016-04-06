#!/bin/bash -x
rulename=${1:-*}
sed -i '\;^// LOG: ;d' rulesets/${rulename}.less
for r in rulesets/${rulename}.less
    do
        file=$(basename $r)
        name=${file%%.less}
        echo $name
        lessc rulesets/${name}.less ${name}.css
        cnx-easybake -v rulesets/${name}.css html/${name}_raw.html /dev/null 2>&1 | sed 's;^;// LOG: ;' >> rulesets/${name}.less
    done  
