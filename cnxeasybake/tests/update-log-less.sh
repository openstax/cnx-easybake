#!/bin/bash
sed -i '/^\/\/ LOG:/d' rulesets/*.less
for r in rulesets/*css; do file=$(basename $r); name=${file%%.css}; echo $name; cnx-easybake -v $r html/${name}_raw.html 2>&1 >/dev/null | sed 's;^;// LOG: ;' >> rulesets/${name}.less; done  
