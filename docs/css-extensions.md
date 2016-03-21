###  CSS3 Syntax for Collation and Numbering - OpenStax easybake ###

## Moving and copying:

Implement parts of the CSS-generated-content spec. Two declarations and
a content function:  

  >move-to: _idstring_  
  >copy-to: _idstring_  
  >content: pending(_idstring_)  

Declarations `move-to` and `copy-to`  will "mark" the  matching node (and all
of its descendants) for moving or copying to the place identified by the
`idstring`.

The CSS function `pending()` is valid as the value of a `content:` declaration,
esp. inside a pseudo-element (`::after` or `::before`). When this node is
reached when walking the HTML tree in recursive descent, the pending moves and
copies land here.

As an extension, since we are targeting output of HTML, rather than another
rendering tree (page or screen display), we will create an actual wrapper node
for each pseudo-element area. In support of this, we are adding additional
declarations:  
  >display: block|inline  
  >class: myclassname  
  >data-type: mydatatype

The class and data-type declarations will set the value of that attribute on
the generated wrapper node. The `display` declaration will make the wrapper
node a `div` or `span`, respectively. (_N.B._ There may be need for block:h1,
block:section, or perhaps wrapper-node: h1|section|div|span|strong instead.)

Note that `move-to:` and `copy-to:` may be used on pseudo-element rules as
well.  This would allow generation of, for example, a title string, in the
context of one node, using local values of counters or content, but moving that
generated node inside a different node elsewhere. The value of this over
string-set is that it generates a _wrapped_ element, rather than only a string.

Note that `copy-to` will modify any 'id' values in the nodes it copies, to keep
them unique within the HTML document tree as a whole. FIXME add details of
heuristic used to make them unique.
