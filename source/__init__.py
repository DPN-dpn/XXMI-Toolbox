from . import updator
from . import convert_shadow
from . import copy_metadata
from . import separate_by_vertex_group

modules = [
    updator,
    convert_shadow,
    copy_metadata,
    separate_by_vertex_group,
]

def register():
    for mod in modules:
        if hasattr(mod, "register"):
            mod.register()

def unregister():
    for mod in reversed(modules):
        if hasattr(mod, "unregister"):
            mod.unregister()