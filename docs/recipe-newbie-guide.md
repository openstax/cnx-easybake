# What are recipes?


# Why do we use it?


# Pipeline Comparison: Docbook vs Recipes

| Docbook  v|s Easybake |
| ------------- | ------------- |
|
**Structural Based**    
By using the slots & skeletons framework you targeting raw html elements created by a content manager and injecting styles using a combination of slots / skeleton, Prince, and custom mixins.

**Styles and Mixins can co-exist**
These mixins can used along with styles in the same .less files. |
Easybake + Recipes

**Design Based**
With Recipes, we are using special rules sets in easybake in the form of .less files that allow manipulation, reorganization, copying, moving, deleting, and more to existing elements on the DOM.  It can also be used to create new elements.

**Styles and Mixins can NOT co-exist currently**
Easybake seeks out the special rule sets or recipes in a specified recipe .less file to use during “baking” process.  Usage of standard CSS in these recipe files will break baking process.  Cosmetic styling and Recipe styling are kept separate.  |


# Recipe Specific CSS
  Common methods w/ troubleshooting & quick how-to ( step by step w/ screenshots)

# General troubleshooting: Common issues


# How to get started: Bake a book
  Checklist .  ( could be a seperate .md file depending on how large this gets. )
