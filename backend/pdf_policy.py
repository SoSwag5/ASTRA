"""Decoded inert-PDF checks; call only inside the resource-limited parser."""


def require_inert_pdf(reader):
    from pypdf.generic import ArrayObject, DictionaryObject, IndirectObject, NameObject

    forbidden_keys = {'/OpenAction', '/AA', '/JS', '/JavaScript', '/EmbeddedFiles',
                      '/EF', '/XFA', '/RichMediaContent', '/RichMediaSettings'}
    forbidden_names = {'/JavaScript', '/Launch', '/EmbeddedFile', '/RichMedia',
                       '/RichMediaExecute', '/SubmitForm', '/ImportData', '/GoToE', '/GoToR'}
    pending = [(reader.trailer, 0)]
    references, containers = set(), set()
    visited = 0
    while pending:
        obj, depth = pending.pop()
        visited += 1
        if depth > 100 or visited > 50_000:
            raise ValueError('Unsupported PDF object complexity')
        if isinstance(obj, IndirectObject):
            identity = (obj.idnum, obj.generation)
            if identity in references:
                continue
            references.add(identity)
            resolved = obj.get_object()
            if resolved is None:
                raise ValueError('Unresolved PDF object')
            pending.append((resolved, depth + 1))
        elif isinstance(obj, DictionaryObject):
            if id(obj) in containers:
                continue
            containers.add(id(obj))
            if forbidden_keys.intersection(obj.keys()):
                raise ValueError('Active or embedded PDF content is unsupported')
            if obj.get('/S') == '/URI':
                uri = str(obj.get('/URI', '')).strip().lower()
                if uri.startswith(('javascript:', 'data:', 'file:')):
                    raise ValueError('Active PDF link is unsupported')
            # raw_get preserves references; following them is cycle/budget bounded.
            pending.extend((obj.raw_get(key), depth + 1) for key in obj.keys())
        elif isinstance(obj, ArrayObject):
            if id(obj) in containers:
                continue
            containers.add(id(obj))
            pending.extend((value, depth + 1) for value in obj)
        elif isinstance(obj, NameObject) and str(obj) in forbidden_names:
            raise ValueError('Active or embedded PDF content is unsupported')
