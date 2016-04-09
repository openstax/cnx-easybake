#!/bin/bash
rulename=${1:-*}
sed -i '\;^// LOG: ;d' rulesets/${rulename}.less
for r in rulesets/${rulename}.less
    do
        file=$(basename $r)
        name=${file%%.less}
        echo $name
        lessc rulesets/${name}.less rulesets/${name}.css
        cnx-easybake -v rulesets/${name}.css html/${name}_raw.html html/${name}_cooked.html 2>&1 | sed 's;^;// LOG: ;' >> rulesets/${name}.less
        touch rulesets/${name}.css
    done  
