###  CSS3 Syntax for Collation and Numbering - OpenStax easybake ###

## Moving and copying:

Implement parts of the CSS-generated-content spec. Two declarations and
a content function:  

    move-to: <bucketname>  
    copy-to: <bucketname>  
    string-set: <stringname> "my string" attr(<attrname>) content()  
    node-set: <setname>

    content: pending(<bucketname>)  string(<stringname>)  nodes(<setname>)

Declarations `move-to` and `copy-to`  will "mark" the  matching node (and all
of its descendants) for moving or copying to the place identified by the
`bucketname`. The two `-set` declarations, `string-set` and `node-set`, serve
to make a reusable copy of their value. The node-set will copy the current node,
while `string-set` assigns a concatenation of all its arguments to the first,
stringname.

The CSS function `pending()` is valid as the value of a `content:` declaration,
esp. inside a pseudo-element (`::after` or `::before`). When this node is
reached when walking the HTML tree in recursive descent, the pending moves and
copies land here. `string(<stringname>)` and `nodes(<setname>)` retrieve  values
stored by `string-set` and `node-set`, respectively. `attr(<attrname>)` evalutes
to the value of an attribute on the current node, while content() (in a string-set)
expands to the textual value of the node contents. In other contexts, it expands
to the node`s current content.

As an extension, since we are targeting output of HTML, rather than another
rendering tree (page or screen display), we will create an actual wrapper node
for each pseudo-element area. In support of this, we are adding additional
declarations:  

    container: div|span|h1|...  
    class: myclassvalue  
    data-type: mydatatypevalue
    attr-my-new-attr: mynewattibute

    sort-by: dl>dt

The class declarations will set the value of that attribute on the generated
wrapper node. The data-*  and attr-* allows for setting any data or other
arbitrary attributes on the wrapper. The `container` declaration will make the
wrapper a node of whatever type you specify, defaulting to div.

Note that `move-to:` and `copy-to:` may be used as part of a pseudo-element rule
as well. In that case, the wrapping node and it's content will be moved or copied
to the declared bucketname, as well. This would allow generation of, for example,
a title string, in the context of one node, using local values of counters or content,
but moving that generated node inside a different node elsewhere. The value of this over
string-set is that it generates a _wrapped_ element, rather than only a string.

The `copy-to` declaration will modify any 'id' values in the nodes it copies,
to keep them unique within the HTML document tree as a whole. FIXME add details
of heuristic used to make them unique.
