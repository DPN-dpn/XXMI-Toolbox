from . import updator
from . import convert_shadow
from . import copy_metadata

modules = [
    convert_shadow,
    updator,
    copy_metadata,
]

def register():
    for mod in modules:
        if hasattr(mod, "register"):
            mod.register()

def unregister():
    for mod in reversed(modules):
        if hasattr(mod, "unregister"):
            mod.unregister()