from copy import deepcopy


def copy_w_id_suffix(elem, suffix="_copy"):
    """Make a deep copy of the provided tree, altering ids."""
    mycopy = deepcopy(elem)
    for id_elem in mycopy.xpath('//*[@id]'):
        id_elem.set('id', id_elem.get('id') + suffix)
    return mycopy
