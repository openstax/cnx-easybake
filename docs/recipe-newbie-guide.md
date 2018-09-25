# What are recipes?


# Why do we use it?


# Pipeline Comparison: Docbook vs Recipes

### Docbook ###

**Structural Based**  
By using the slots & skeletons framework you targeting raw html elements created by a content manager and injecting styles using a combination of slots / skeleton, Prince, and custom mixins.

**Styles and Mixins can co-exist**  
These mixins can used along with styles in the same .less files.

### Easybake ###

**Design Based**  
With Recipes, we are using special rules sets in easybake in the form of .less files that allow manipulation, reorganization, copying, moving, deleting, and more to existing elements on the DOM.  It can also be used to create new elements.

**Styles and Mixins can NOT co-exist currently**  
Easybake seeks out the special rule sets or recipes in a specified recipe .less file to use during “baking” process.  Usage of standard CSS in these recipe files will break baking process.  Cosmetic styling and Recipe styling are kept separate.  


# Recipe Specific CSS / Methods
This section contains information, thoughts, and limitations on some commonly used methods in easybake as well as a quick how-to on using them.  

**`Move-to:`**  Moves all selected elements to a target destination in one pass.

- ***Quick how to use:***
   1. Create a selector for either an existing element or create one using ::after.
   1. Use the move-to: attribute inside the selector rule set, and give it a variable name. Example: move-to:(my-move-to-element);
   1. (Optional) Assign class name, ( class: “ “ ) , Additional content ( content: “ “ ) , etc. as needed.  
   1. Create a selector for its destination.  This is where our content will be moved to on the DOM.
   1. Inside the destination selector, create a content attribute and pass in pending element you want to move.   
Example:  content: pending(my-move-to-element);

- ***Usage notes:***  
Is good for moving many of the elements with same selector to target locations in DOM.


- ***Limitations:***  
  - Is actually able to use a string as an input, but shouldn’t because it’s partner method “ pending() “ is meant to accept variables and not hard coded strings.  Should be listed as bug fix.

  - Will always create a container, even if you don’t want one.  Will default to a div unless you specify with a “ container: yourElement “ rule.

**`Copy-to:`**  Copies one instance of a selector to a target destination in one pass.

- ***Quick how to use:***
  - Steps are identical to move-to with one major difference… see limitations.


- ***Limitations:***  
  - Works much like move-to, except it can only move ONE instance of a selector.   All others will be ignored.

  - Move-to is a better choice usually.

**`Node-set:`**  Creates a reuseable variable for an element that can be copied to target destination(s).

- ***Quick how to use:***
   1. Create selector for an element that already exists.  See Passes():
   1. Use the node-set attribute inside the selector rule set, and give it a variable name.  Example:  node-set(my-node-element);
   1. Create a selector for its destination.  This is where our content will be moved to on the DOM.
   1. Inside destination selector, create content attribute and pass in the node variable.  Example: content: nodes(my-node-element);


- ***Limitations:***  
  - None .. known?

**`String-set:`**  Construct a string and create variable that can be copied to target destinations(s).  

- ***Quick how to use:***
   1. Create selector for string-set variable.  
   1. Use string-set attribute to create a variable name and construct string.

- ***Example:***  
   1. Variable name            1. String  
string-set: my-string-set-element “This is pretty shwifty string.”


   1. Create a selector for its destination.  This is where our string will be copied to on the DOM.  
   1. Inside destination selector, create content attribute and pass in the string variable.

- ***Example:***   
content(   string(my-string-set-element) );

- ***Usage notes:***  
It’s very common to create concatenated strings using string-set.  You can create combine multiple strings, counters, variables, into a single string.  Use the proper formatting when passing multiple inputs. )

- ***Example:***  
string-set: my-concatenated-string-variable "Figure" “ “  counter(figure-number) “ “ “Section“ “ “ counter(section-number);

  This will translate to:

  “Figure 1.1 Section 1.1”

  Note where the spaces are ( “ “ will translate to blank spaces, they are included in the above example.

  Alternatively, you can include spaces in the strings coming before when possible.

- ***Example:***  
  `string-set: target-label "Figure " counter(figure-number) “ Section “ counter(section-number);

  Still translates to:

  “Figure 1.1 Section 1.1”`

- ***Limitations:***  
  - None… known?

  Common methods w/ troubleshooting & #quick how-to ( step by step w/ #screenshots)

# General troubleshooting: Common issues

- Content must be defined before placing it (Put the 'what' before the 'where')
    Example: move-to: must come before pending()
- When setting the container method, it must come before the content property
- Make sure that there are no spaces between the function name and the argument in parentheses
    Example: pending(name) ← YAY   pending  (name) ← :(
- container, move-to, etc. are called methods. If you get the ‘missing method ____ ‘ traceback, it’s probably a typo
- Traceback → ‘can’t append parent to itself’: You may have forgotten to create a container (don’t forget ::after
- For move-to, don’t use quotations. If you do, it won’t throw an error as long as your move-to value and your pending parameter matches, BUT without quotations it improves readability.


# How to get started: Bake a book
  Checklist .  ( could be a seperate .md file depending on how large this gets. )
